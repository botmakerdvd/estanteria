#!/usr/bin/env python3
# ir_launcher.py
# Orquestador del Show (Versión PROXY - SOLO FOTOS)

import evdev
from evdev import UInput, ecodes
import subprocess
import time
import os
import signal
import sys
import atexit
import threading
import requests

try:
    from rf_control import RFManager
except ImportError:
    RFManager = None

# ========= MAPA DE CÓDIGOS (NEC - Tu Mando) =========
CODES = {
    0x0c: "BTN_1",  # 1 -> Torre Reloj
    0x18: "BTN_2",  # 2 -> Libios
    0x5e: "BTN_3",  # 3 -> Pendiente
    0x08: "BTN_4",  # 4 -> Power Rangers 1
    0x1c: "BTN_5",  # 5 -> Power Rangers 2
    0x5a: "BTN_6",  # 6 -> Gabarra 24
    0x42: "BTN_7",  # 7 -> Copa 24
    0x52: "BTN_8",  # 8 -> Supercopa 15
    0x4a: "BTN_9",  # 9 -> Supercopa 22
    0x16: "BTN_0",  # 0 -> VUELTA A KODI
}

SHOWS = {
    "BTN_1": ["python3", "torre_reloj.py"],
    "BTN_2": ["python3", "libios.py"],
    "BTN_4": ["python3", "power_rangers.py"],
    "BTN_0": "KODI"
}

current_show_process = None
rf_server_process = None
ui = None # Dispositivo Virtual
last_press_time = 0
DEBOUNCE_SECONDS = 1.0

def cleanup_all():
    """Limpieza general al salir."""
    global rf_server_process, ui
    if rf_server_process:
        print("🛑 Deteniendo servidor RF...")
        try:
            rf_server_process.terminate()
        except: pass
    if ui:
        ui.close()

atexit.register(cleanup_all)

def monitor_loop():
    """Hilo secundario que vigila si el SHOW ha terminado para volver al Slideshow."""
    global current_show_process
    while True:
        time.sleep(2)
        # Si hay un proceso de show activo y ha terminado...
        if current_show_process and current_show_process.poll() is not None:
            print("🎬 Show terminado. Volviendo a base (Slideshow)...")
            current_show_process = None 

            if RFManager:
                try: RFManager().reset_sequence()
                except: pass

            launch_slideshow()


def start_rf_server():
    global rf_server_process
    print("📡 Iniciando rf_server.py...")
    rf_server_process = subprocess.Popen(["python3", "rf_server.py"])
    time.sleep(1.5)

def clean_hyperion():
    print("💡 Limpiando Hyperion (Prioridades 50 y 64)...")
    try:
        requests.post("http://localhost:8090/json-rpc",
                      json={"command": "clear", "priority": 50}, timeout=0.2)
        requests.post("http://localhost:8090/json-rpc",
                      json={"command": "clear", "priority": 64}, timeout=0.2)
    except:
        pass

def perform_rf_handshake():
    if not RFManager: return
    print("🤝 Realizando RF Handshake (Reset Inicial)...")
    try:
        rf = RFManager()
        rf.send("onoff"); time.sleep(1.0)
        rf.send("onoff"); time.sleep(1.0)
        rf.send("funct8"); time.sleep(2.0)
    except: pass

def kill_active_show():
    global current_show_process
    print("🧹 Limpiando procesos (MPV, Shows, Kodi)...")

    if RFManager:
        try:
            rf = RFManager()
            rf.reset_sequence()
        except: pass

    clean_hyperion()

    if current_show_process:
        try:
            os.killpg(os.getpgid(current_show_process.pid), signal.SIGTERM)
        except: pass
        current_show_process = None

    # Escoba
    subprocess.call(["pkill", "-f", "torre_reloj.py"])
    subprocess.call(["pkill", "-f", "libios.py"])
    subprocess.call(["pkill", "-f", "power_rangers.py"])
    subprocess.call(["pkill", "-f", "mpv"])
    subprocess.call(["pkill", "-f", "kodi"])

def launch_slideshow():
    """Mata todo y lanza MPV SOLO CON FOTOS."""
    perform_rf_handshake()

    print("🌅 Iniciando Slideshow (Solo Fotos + Ken Burns)...")
    kill_active_show()

    # --- NUEVA LOGICA DE FILTRADO ---
    # Creamos una lista de reproduccion temporal filtrando solo imágenes
    img_dir = "/media/imagenes/"
    playlist_path = "/tmp/playlist_fotos.m3u"
    valid_ext = ('.jpg', '.jpeg', '.png', '.bmp', '.webp')

    try:
        # Buscamos archivos recursivamente o solo en la raiz
        with open(playlist_path, 'w') as f:
            for root, dirs, files in os.walk(img_dir):
                for file in files:
                    if file.lower().endswith(valid_ext):
                        # Escribimos la ruta completa en el archivo playlist
                        f.write(os.path.join(root, file) + "\n")
        print("✅ Playlist de fotos generada correctamente.")
    except Exception as e:
        print(f"❌ Error generando playlist: {e}")
        return # Salimos si falla esto

    # Ken Burns Effect (Zoom lento) + Playlist generada
    cmd = [
        "mpv",
        f"--playlist={playlist_path}",  # <--- Usamos la lista filtrada
        "--fs", "--no-osc", "--keep-open=yes", "--loop-playlist=inf",
        "--image-display-duration=10",
        "--shuffle",
        "--vf=lavfi=[scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,zoompan=z='min(zoom+0.0010,1.2)':d=250:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)']"
    ]
    
    # Lanzamos MPV
    subprocess.Popen(cmd, preexec_fn=os.setsid, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def launch_show(cmd_list):
    global current_show_process
    perform_rf_handshake()
    print(f"🚀 Lanzando show: {cmd_list}")
    kill_active_show()
    current_show_process = subprocess.Popen(cmd_list, preexec_fn=os.setsid)

def main():
    print("=== ORQUESTADOR PROXY (Anti-Secuestro Kodi) ===")

    try:
        subprocess.run(["ir-keytable", "-p", "all"], check=False)
    except: pass

    start_rf_server()

    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()

    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    ir_device = None
    for dev in devices:
        if "gpio_ir" in dev.name.lower():
            ir_device = dev
            break

    if not ir_device:
        print("❌ Error: No se encuentra 'gpio_ir_recv'")
        return

    print(f"🔒 Capturando (GRAB) dispositivo: {ir_device.name}")

    try:
        global ui
        ui = UInput.from_device(ir_device, name="mand_virtual_proxy")
        ir_device.grab()

        print("✅ Proxy activo. Reenviando teclas no mapeadas...")

        # Arrancar Slideshow (SOLO FOTOS) al inicio
        launch_slideshow()
        
        for event in ir_device.read_loop():
            forward = True

            if event.type == evdev.ecodes.EV_MSC and event.value in CODES:
                btn_name = CODES[event.value]
                now = time.time()
                global last_press_time

                if (now - last_press_time) > DEBOUNCE_SECONDS:
                    print(f"🎯 Detectado comando maestro: {btn_name}")
                    last_press_time = now

                    action = SHOWS.get(btn_name)
                    if btn_name == "BTN_0":
                        launch_slideshow()
                        forward = False
                    elif action and isinstance(action, list):
                        launch_show(action)
                        forward = False
                else:
                    print(f"⏳ Ignorando rebote de {btn_name}")
                    forward = False 

            if forward:
                ui.write_event(event)
                ui.syn()

    except OSError:
        print("❌ Error: Posiblemente otro proceso ya tiene el GRAB. Mata Kodi primero.")
    except KeyboardInterrupt:
        print("\n👋 Saliendo...")
    finally:
        cleanup_all()

if __name__ == "__main__":
    main()
