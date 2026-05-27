#Jarvis · PY
#!/usr/bin/env python3
"""
jarvis.py — Automatización con doble aplauso.
Escucha el micrófono, detecta dos aplausos, saluda por voz,
abre Spotify (y lo minimiza) y lanza las apps configuradas.
 
Uso: python jarvis.py
"""
 
import os
import sys
import time
import platform
import subprocess
import threading
 
import numpy as np
import sounddevice as sd
 
_dir_actual = os.path.dirname(os.path.abspath(__file__))
_env_path = None
 
for nombre_archivo in [".env", "env"]:
    posible_ruta = os.path.join(_dir_actual, nombre_archivo)
    if os.path.isfile(posible_ruta):
        _env_path = posible_ruta
        break
 
if _env_path:
    print(f"[Jarvis] Archivo de configuración detectado en: {os.path.basename(_env_path)}")
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _v_clean = _v.strip().strip('"').strip("'").strip()
                os.environ[_k.strip()] = _v_clean
else:
    print("\n[ALERTA] ¡No encontré ningún archivo '.env' ni 'env' en tu carpeta!")
    print(f"Buscé en: {_dir_actual}\n")
 
#Configuración
PLATFORM    = platform.system()
NOMBRE      = os.getenv("JARVIS_NOMBRE", "").strip()
SPOTIFY_URL = os.getenv("JARVIS_SPOTIFY_URL", "spotify:track:2zYzyRzz6pRmhPzyfMEC8s")
APPS        = [a.strip() for a in os.getenv("JARVIS_APPS", "Terminal,Claude").split(",") if a.strip()]
THRESHOLD   = float(os.getenv("JARVIS_THRESHOLD", "0.03"))
VOICE_LANG  = os.getenv("JARVIS_VOICE_LANG", "es")
VOICE_RATE  = os.getenv("JARVIS_VOICE_RATE", "148")
 
#Parámetros del micrófono
SAMPLE_RATE   = 48000
BLOCK_SIZE    = int(SAMPLE_RATE * 0.05)
COOLDOWN      = 0.15
DOUBLE_WINDOW = 2.0
MIC_DEVICE    = None
MIC_CHANNELS  = 1
 
#voz
def speak(message: str) -> None:
    if PLATFORM == "Darwin":
        subprocess.run(["say", "-v", os.getenv("JARVIS_VOICE_MAC", "Monica"), "-r", VOICE_RATE, message], check=False)
    elif PLATFORM == "Windows":
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", int(VOICE_RATE))
            for voice in engine.getProperty("voices"):
                if VOICE_LANG.lower() in voice.id.lower():
                    engine.setProperty("voice", voice.id)
                    break
            engine.say(message)
            engine.runAndWait()
        except ImportError:
            pass
    else:
        try:
            subprocess.run(["espeak-ng", "-v", f"{VOICE_LANG}+f3", "-s", VOICE_RATE, message], check=False)
        except FileNotFoundError:
            print(f"[TTS Error] espeak-ng no instalado.")
 
#Abrir aplicaciones
def open_app(app_name: str) -> None:
    if PLATFORM == "Darwin":
        subprocess.Popen(["open", "-a", "Terminal" if app_name.lower() == "terminal" else app_name])
    elif PLATFORM == "Windows":
        if app_name.lower() in ("cmd", "terminal"):
            subprocess.Popen("start cmd", shell=True)
        else:
            subprocess.Popen(["start", "", app_name], shell=True)
    else:
        linux_apps = {
            "terminal":           "x-terminal-emulator",
            "claude":             "claude-desktop",
            "spotify":            "spotify",
            "chrome":             "google-chrome",
            "code":               "code",
            "vscode":             "code",
            "vs code":            "code",
            "visual studio code": "code",
        }
        
        target = app_name.lower()
        cmd = linux_apps.get(target, app_name)
        
        try:
            subprocess.Popen([cmd])
            return
        except FileNotFoundError:
            pass

        if "code" in target:
            for alt_path in ["/snap/bin/code", "/usr/bin/code"]:
                if os.path.exists(alt_path):
                    subprocess.Popen([alt_path])
                    return
                    
        try:
            subprocess.Popen(cmd, shell=True)
        except Exception:
            print(f"[Error] No se pudo abrir '{app_name}' en Ubuntu.")
 
def open_spotify() -> None:
    print(f"[Jarvis] Abriendo Spotify: {SPOTIFY_URL}")
    if PLATFORM == "Darwin":
        subprocess.Popen(["open", SPOTIFY_URL])
    elif PLATFORM == "Windows":
        subprocess.Popen(["start", SPOTIFY_URL], shell=True)
    else:
        try:
            subprocess.Popen(["xdg-open", SPOTIFY_URL])
        except Exception:
            subprocess.Popen(["spotify"])
        
        threading.Thread(target=_minimize_spotify_linux, daemon=True).start()

def _minimize_spotify_linux() -> None:
    time.sleep(2.5)
    try:
        subprocess.run(["xdotool", "search", "--onlyvisible", "--class", "spotify", "windowminimize"], check=False)
        print("[Jarvis] Spotify enviado a segundo plano (minimizado).")
    except FileNotFoundError:
        print("[Jarvis] Nota: Instala xdotool (sudo apt install xdotool) para minimizar.")
 
def open_apps_and_url() -> None:
    open_spotify()
    time.sleep(0.8)
    for app in APPS:
        print(f"[Jarvis] Abriendo: {app}")
        open_app(app)
        time.sleep(0.8)
 
#Secuencia de bienvenida
def welcome_sequence() -> None:
    greeting = f"Bienvenido a casa{', ' + NOMBRE if NOMBRE else ''}."
    print(f"\n[Jarvis] ¡Doble aplauso confirmado! Iniciando secuencia...")
    print(f"[Jarvis] Diciendo: {greeting}")
 
    threading.Thread(target=speak, args=(greeting,), daemon=True).start()
    open_apps_and_url()
    print("[Jarvis] Secuencia completa. Escuchando...\n")
 
#Detección de aplausos
_last_rms         = 0.0
_clap_times       = []
_sequence_running = False
 
def audio_callback(indata: np.ndarray, frames: int, time_info, status) -> None:
    global _last_rms, _clap_times, _sequence_running
 
    if _sequence_running:
        return
 
    if indata.shape[1] > 1:
        mono = indata.mean(axis=1)
    else:
        mono = indata[:, 0]
        
    rms = float(np.sqrt(np.mean(mono ** 2)))
 
    is_clap = rms > THRESHOLD and _last_rms < THRESHOLD * 0.5
    _last_rms = rms
 
    if not is_clap:
        return
 
    now = time.monotonic()
    _clap_times = [t for t in _clap_times if now - t <= DOUBLE_WINDOW]
 
    if _clap_times and (now - _clap_times[-1]) < COOLDOWN:
        return
 
    _clap_times.append(now)
    print(f"[Jarvis] Aplauso real detectado (RMS={rms:.3f}) — En ventana: {len(_clap_times)}")
 
    if len(_clap_times) >= 2:
        _clap_times.clear()
        _sequence_running = True
        print("[Jarvis] ¡Lanzando secuencia!")
        threading.Thread(target=_run_sequence, daemon=True).start()
 
def _run_sequence() -> None:
    global _sequence_running
    try:
        welcome_sequence()
    finally:
        _sequence_running = False
 
def main() -> None:
    print("=" * 60)
    print("  Jarvis — Automatización con doble aplauso")
    print("=" * 60)
    print(f"  Sistema   : {PLATFORM}")
    print(f"  Usuario   : {NOMBRE or '(no configurado)'}")
    print(f"  Spotify   : {SPOTIFY_URL}")
    print(f"  Apps      : {', '.join(APPS)}")
    print(f"  Umbral    : {THRESHOLD}")
    print(f"  Micrófono : dispositivo {MIC_DEVICE} ({MIC_CHANNELS} canales)")
    print("=" * 60)
    print("  ¡Aplaudí dos veces para activar! Ctrl+C para salir.\n")
 
    try:
        with sd.InputStream(
            device=MIC_DEVICE,
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            channels=MIC_CHANNELS,
            dtype="float32",
            callback=audio_callback,
        ):
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[Jarvis] Cerrando. ¡Hasta luego!")
    except Exception as exc:
        print(f"[Jarvis] Error de audio: {exc}")
        sys.exit(1)
 
if __name__ == "__main__":
    main()