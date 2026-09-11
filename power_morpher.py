#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# power_morpher.py
# Servidor UDP para efectos mágicos de iluminación Morpher <-> Estantería Power Rangers

import socket
import time
import math
import random
import threading
import sys
import os
import subprocess

try:
    import requests
except ImportError:
    requests = None

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ========= IMPORTACIÓN DE LAYOUT Y LEDS =========
try:
    from layout import INDEX, N
except ImportError:
    INDEX = {}
    N = 153

# ========= CONFIGURACIÓN DE RED Y HYPERION =========
UDP_HOST = "0.0.0.0"
UDP_PORT = 5005
HYPERION_URL = "http://localhost:8090/json-rpc"
PRIORITY = 50
ORIGIN = "PowerMorpherMagic"

# ========= CONFIGURACIÓN DE AUDIO DE LA ESTANTERÍA =========
# Dispositivo de salida de audio para reproducir rugidos y Megazord:
# Ejemplos en Raspberry Pi:
#   - HDMI:                "alsa/hdmi:CARD=vc4hdmi,DEV=0"
#   - Jack 3.5mm / Cascos: "alsa/sysdefault:CARD=Headphones"
#   - USB DAC:             "alsa/sysdefault:CARD=Set"
#   - Predeterminado ALSA: "default" o "" (vacío)
AUDIO_DEVICE = "default"

# ========= PALETA DE COLORES OFICIAL RANGERS & ZORDS =========
COLOR_MAP = {
    "RED":    (255, 0, 0),
    "YELLOW": (255, 180, 0),
    "BLACK":  (160, 0, 255),  # Púrpura/Místico para Black Ranger
    "BLUE":   (0, 80, 255),
    "PINK":   (255, 15, 140),
    "WHITE":  (220, 240, 255),
}

RANGERS_ORDER = ["RED", "BLUE", "YELLOW", "PINK", "BLACK", "WHITE"]
WHITE_SOFT = (220, 235, 255)

# ========= MAPEO DE ZONAS Y LEDS =========
Z2_STRIP = INDEX.get("T_T", list(range(70, 88)))   # Balda Rangers
Z1_STRIP = INDEX.get("Z1_T", list(range(106, 124))) # Balda Zords
Z3_STRIP = INDEX.get("M_T", list(range(35, 53)))   # Balda Media
Z4_STRIP = INDEX.get("B_T", list(range(0, 18)))    # Balda Inferior

# Mapeo de LEDs por Ranger (Zona 2)
RANGER_LEDS = {
    "RED":    Z2_STRIP[14:18] if len(Z2_STRIP) >= 18 else [84, 85, 86, 87],
    "YELLOW": Z2_STRIP[11:14] if len(Z2_STRIP) >= 14 else [81, 82, 83],
    "BLACK":  Z2_STRIP[10:11] if len(Z2_STRIP) >= 11 else [80],
    "PINK":   Z2_STRIP[8:10]  if len(Z2_STRIP) >= 10 else [78, 79],
    "BLUE":   Z2_STRIP[5:8]   if len(Z2_STRIP) >= 8  else [75, 76, 77],
    "WHITE":  Z2_STRIP[0:5]   if len(Z2_STRIP) >= 5  else [70, 71, 72, 73, 74],
}

# Mapeo de LEDs por Zord (Zona 1)
ZORD_LEDS = {
    "RED":    Z1_STRIP[14:18] if len(Z1_STRIP) >= 18 else [120, 121, 122, 123],
    "YELLOW": Z1_STRIP[11:14] if len(Z1_STRIP) >= 14 else [117, 118, 119],
    "BLACK":  Z1_STRIP[10:11] if len(Z1_STRIP) >= 11 else [116],
    "PINK":   Z1_STRIP[8:10]  if len(Z1_STRIP) >= 10 else [114, 115],
    "BLUE":   Z1_STRIP[5:8]   if len(Z1_STRIP) >= 8  else [111, 112, 113],
    "WHITE":  Z1_STRIP[0:5]   if len(Z1_STRIP) >= 5  else [106, 107, 108, 109, 110],
}

COL_LEFT  = (INDEX.get("B_L", []) + INDEX.get("M_L", []) + INDEX.get("T_L", []))
COL_RIGHT = (INDEX.get("B_R", []) + INDEX.get("M_R", []) + INDEX.get("T_R", []))

# Columnas laterales continuas de los 2 cajones superiores donde están los juguetes (Rangers Zona 2 + Zords Zona 1)
TOYS_COL_LEFT  = INDEX.get("T_L", []) + INDEX.get("Z1_L", [])
TOYS_COL_RIGHT = INDEX.get("T_R", []) + INDEX.get("Z1_R", [])

# ========= ESTADO PERSISTENTE DE ILUMINACIÓN =========
LIT_STATE = {}  # { led_index: (r, g, b) }
current_effect_token = 0

def send_frame(pixels):
    """Envía un frame completo de LEDs a Hyperion (Prioridad 50)."""
    flat = []
    for r, g, b in pixels:
        flat.extend([int(max(0, min(255, r))), int(max(0, min(255, g))), int(max(0, min(255, b)))])
    try:
        requests.post(HYPERION_URL, json={
            "command": "color", "color": flat,
            "priority": PRIORITY, "origin": ORIGIN, "duration": -1
        }, timeout=0.05)
    except: pass

def render_base_frame():
    """Genera el frame base incorporando los LEDs persisentes activados."""
    pixels = [(0, 0, 0)] * N
    for idx, col in LIT_STATE.items():
        if 0 <= idx < N:
            pixels[idx] = col
    return pixels

def update_persistent_frame():
    """Actualiza el frame estático persistente en Hyperion."""
    send_frame(render_base_frame())

# ========= FASE 1 APERTURA: ESTROBOSCÓPICO ROJO COLUMNAS =========
def run_morph_intro_effect(token):
    global current_effect_token
    print("⚡ [FASE 1 APERTURA] ¡A metamorfosearse! Estroboscópico rojo en columnas laterales...", flush=True)

    fps = 30
    duration = 2.2
    total_frames = int(duration * fps)

    for frame in range(total_frames):
        if current_effect_token != token:
            return

        pixels = render_base_frame()
        strobe_state = (frame % 2 == 0)

        for k, idx in enumerate(COL_LEFT + COL_RIGHT):
            if 0 <= idx < N:
                if strobe_state:
                    pixels[idx] = (255, 0, 0) if (k % 3 != 0) else WHITE_SOFT
                else:
                    pixels[idx] = (40, 0, 0)

        send_frame(pixels)
        time.sleep(1.0 / fps)

# ========= FASE 2 APERTURA / EFECTO 1: METAMORFOSIS RANGER (MORPH) =========
def run_morph_effect(ranger_name, token):
    global current_effect_token
    print(f"⚡ [EFECTO RANGER] Metamorfosis para {ranger_name}...", flush=True)
    color = COLOR_MAP.get(ranger_name, (255, 0, 0))
    r_target = RANGER_LEDS.get(ranger_name, [])

    if r_target and Z2_STRIP:
        target_indices_in_strip = [Z2_STRIP.index(i) for i in r_target if i in Z2_STRIP]
        mid_strip_pos = sum(target_indices_in_strip) / len(target_indices_in_strip) if target_indices_in_strip else len(Z2_STRIP) / 2
    else:
        mid_strip_pos = len(Z2_STRIP) / 2 if Z2_STRIP else 0

    dist_left = mid_strip_pos
    dist_right = (len(Z2_STRIP) - 1) - mid_strip_pos if Z2_STRIP else 1

    fps = 30
    duration = 1.6  # Reducido de 2.8s a 1.6s para un camino mucho más rápido y dinámico
    total_frames = int(duration * fps)
    shout_played = False

    for frame in range(total_frames):
        if current_effect_token != token:
            return

        t = frame / total_frames
        pixels = render_base_frame()

        if t < 0.25:
            # FASE 1: Subida de energía supersónica por columnas (0 a 0.40s)
            prog = t / 0.25
            head_l = int(prog * len(COL_LEFT)) if COL_LEFT else 0
            head_r = int(prog * len(COL_RIGHT)) if COL_RIGHT else 0

            for k in range(len(COL_LEFT)):
                dist = head_l - k
                if 0 <= dist < 6:
                    val = 1.0 - (dist / 6.0)
                    idx = COL_LEFT[k]
                    c = WHITE_SOFT if dist < 2 else color
                    if 0 <= idx < N: pixels[idx] = (int(c[0]*val), int(c[1]*val), int(c[2]*val))

            for k in range(len(COL_RIGHT)):
                dist = head_r - k
                if 0 <= dist < 6:
                    val = 1.0 - (dist / 6.0)
                    idx = COL_RIGHT[k]
                    c = WHITE_SOFT if dist < 2 else color
                    if 0 <= idx < N: pixels[idx] = (int(c[0]*val), int(c[1]*val), int(c[2]*val))

        elif t < 0.55:
            # FASE 2: Carrera rápida por la balda hacia el Ranger (0.40s a 0.88s)
            prog = (t - 0.25) / 0.30
            pos_left = int(prog * dist_left)
            pos_right = (len(Z2_STRIP) - 1) - int(prog * dist_right)

            for k in range(len(Z2_STRIP)):
                if k <= pos_left:
                    idx = Z2_STRIP[k]
                    dist = pos_left - k
                    if dist < 5:
                        val = 1.0 - (dist / 5.0)
                        c = WHITE_SOFT if dist < 1 else color
                        if 0 <= idx < N: pixels[idx] = (int(c[0]*val), int(c[1]*val), int(c[2]*val))

            for k in range(len(Z2_STRIP) - 1, -1, -1):
                if k >= pos_right:
                    idx = Z2_STRIP[k]
                    dist = k - pos_right
                    if dist < 5:
                        val = 1.0 - (dist / 5.0)
                        c = WHITE_SOFT if dist < 1 else color
                        if 0 <= idx < N: pixels[idx] = (int(c[0]*val), int(c[1]*val), int(c[2]*val))

        elif t < 0.85:
            # FASE 3: ¡Impacto sobre el Ranger! (~0.88s) -> ¡Disparo inmediato del grito!
            if not shout_played:
                for i in r_target:
                    LIT_STATE[i] = color
                threading.Thread(target=play_ranger_shout, args=(ranger_name,), daemon=True).start()
                shout_played = True

            prog = (t - 0.55) / 0.30
            pulse = 0.85 + 0.15 * math.sin(prog * math.pi * 6)
            for i in r_target:
                if 0 <= i < N:
                    pixels[i] = (int(color[0] * pulse), int(color[1] * pulse), int(color[2] * pulse))

        else:
            # FASE 4: Consolidación del color puro e intenso
            for i in r_target:
                if 0 <= i < N: pixels[i] = color

        send_frame(pixels)
        time.sleep(1.0 / fps)

    if current_effect_token == token:
        for i in r_target:
            LIT_STATE[i] = color
        update_persistent_frame()
        print(f"✨ [PERSISTENCIA] Ranger {ranger_name} activado y encendido permanentemente.", flush=True)

# ========= REPRODUCCIÓN DE AUDIO LOCAL (RUGIDOS Y MEGAZORD) =========
current_audio_process = None

def stop_current_audio():
    """Detiene cualquier audio local en reproducción si se interrumpe el efecto."""
    global current_audio_process
    if current_audio_process and current_audio_process.poll() is None:
        try:
            current_audio_process.terminate()
        except Exception:
            pass
        current_audio_process = None

def play_sound_file(file_path):
    """Reproduce un archivo de audio local usando mpv o aplay según la configuración."""
    global current_audio_process
    if not file_path or not os.path.exists(file_path):
        print(f"⚠️ [AUDIO] Archivo no encontrado: {file_path}", flush=True)
        return
    print(f"🔊 [AUDIO ESTANTERÍA] Reproduciendo: {os.path.basename(file_path)}", flush=True)
    try:
        if sys.platform != "win32":
            # En Linux / Raspberry Pi
            if AUDIO_DEVICE and AUDIO_DEVICE.startswith("alsa/"):
                cmd = ["mpv", "--no-video", "--really-quiet", "--volume=100", f"--audio-device={AUDIO_DEVICE}", file_path]
            elif AUDIO_DEVICE:
                cmd = ["aplay", "-q", "-D", AUDIO_DEVICE, file_path]
            else:
                if file_path.lower().endswith(".wav"):
                    cmd = ["aplay", "-q", file_path]
                else:
                    cmd = ["mpv", "--no-video", "--really-quiet", file_path]
            current_audio_process = subprocess.Popen(cmd)
        else:
            # Fallback en Windows
            try:
                import winsound
                winsound.PlaySound(file_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                current_audio_process = subprocess.Popen(["powershell", "-c", f"(New-Object Media.SoundPlayer '{file_path}').PlaySync()"])
    except Exception as e:
        print(f"⚠️ [AUDIO ERROR] Fallo al reproducir audio: {e}", flush=True)

def find_ranger_shout(ranger_name):
    """Localiza el archivo de grito post-metamorfosis (_g.wav) para el Ranger."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    name_lower = ranger_name.lower().strip()
    candidates = [
        os.path.join(base_dir, "audios_power_rangers", f"{name_lower}_g.wav"),
        os.path.join(base_dir, "audios_power_rangers", f"{name_lower}_grito.wav"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

def play_ranger_shout(ranger_name):
    """Reproduce el grito de batalla del Ranger tras morfearse."""
    shout_file = find_ranger_shout(ranger_name)
    if shout_file:
        play_sound_file(shout_file)
    else:
        print(f"⚠️ [AUDIO] No se encontró archivo de grito para Ranger {ranger_name}", flush=True)

def find_zord_sound(ranger_name):
    """Localiza el archivo de audio para el Zord (rojo, azul, amarillo, rosa, negro, blanco, megazord)."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    name_lower = ranger_name.lower().strip()

    candidates = [
        os.path.join(base_dir, "audios_power_rangers", f"{name_lower}_r.wav"),
        os.path.join(base_dir, "audios_power_rangers", f"{name_lower}.wav"),
        os.path.join(base_dir, "sonidos", f"zord_{name_lower}.wav"),
        os.path.join(base_dir, "sonidos", f"{name_lower}.wav")
    ]
    if name_lower == "megazord":
        candidates.insert(0, os.path.join(base_dir, "audios_power_rangers", "megazord_r.wav"))

    for path in candidates:
        if os.path.exists(path):
            return path
    return None

def play_zord_sound(ranger_name):
    sound_file = find_zord_sound(ranger_name)
    if sound_file:
        play_sound_file(sound_file)
    else:
        print(f"⚠️ [AUDIO] No se encontró archivo de rugido para Zord {ranger_name}", flush=True)

# ========= EFECTO 2: INVOCACIÓN ZORD (ZORD) =========
def run_zord_effect(ranger_name, token):
    global current_effect_token
    print(f"🐉 [EFECTO ZORD] Invocación para Zord {ranger_name}...", flush=True)
    color = COLOR_MAP.get(ranger_name, (255, 0, 0))
    z_target = ZORD_LEDS.get(ranger_name, [])
    r_target = RANGER_LEDS.get(ranger_name, [])

    # Asegurar que el Ranger del Zord SIEMPRE quede registrado en LIT_STATE desde el inicio
    for i in r_target:
        LIT_STATE[i] = color

    if z_target and Z1_STRIP:
        target_indices = [Z1_STRIP.index(i) for i in z_target if i in Z1_STRIP]
        mid_target_pos = sum(target_indices) / len(target_indices) if target_indices else len(Z1_STRIP) / 2
    else:
        mid_target_pos = len(Z1_STRIP) / 2 if Z1_STRIP else 0

    fps = 30
    duration = 2.8
    total_frames = int(duration * fps)
    sound_played = False

    for frame in range(total_frames):
        if current_effect_token != token:
            return

        t = frame / total_frames
        pixels = render_base_frame()

        # El Ranger NUNCA se apaga durante la llamada al Zord: encendido continuo
        for i in r_target:
            if 0 <= i < N:
                pixels[i] = color

        if t < 0.35:
            # FASE 1: Subida de energía por columnas laterales
            prog = t / 0.35
            h_left = int(prog * len(COL_LEFT))
            h_right = int(prog * len(COL_RIGHT))

            for k in range(h_left):
                idx = COL_LEFT[k]
                if 0 <= idx < N: pixels[idx] = color
            if 0 < h_left <= len(COL_LEFT):
                top_idx = COL_LEFT[h_left - 1]
                if 0 <= top_idx < N: pixels[top_idx] = WHITE_SOFT

            for k in range(h_right):
                idx = COL_RIGHT[k]
                if 0 <= idx < N: pixels[idx] = color
            if 0 < h_right <= len(COL_RIGHT):
                top_idx = COL_RIGHT[h_right - 1]
                if 0 <= top_idx < N: pixels[top_idx] = WHITE_SOFT

        elif t < 0.65:
            # FASE 2: Cruce Horizontal Adaptativo hacia el Zord en Z1_STRIP
            prog = (t - 0.35) / 0.30
            for i in COL_LEFT + COL_RIGHT:
                if 0 <= i < N: pixels[i] = color

            pos_left = int(prog * mid_target_pos)
            pos_right = len(Z1_STRIP) - 1 - int(prog * (len(Z1_STRIP) - 1 - mid_target_pos))

            for k in range(pos_left + 1):
                idx = Z1_STRIP[k]
                dist = pos_left - k
                if dist < 5:
                    val = 1.0 - (dist / 5.0)
                    c = WHITE_SOFT if dist < 1 else color
                    if 0 <= idx < N: pixels[idx] = (int(c[0]*val), int(c[1]*val), int(c[2]*val))

            for k in range(len(Z1_STRIP) - 1, pos_right - 1, -1):
                idx = Z1_STRIP[k]
                dist = k - pos_right
                if dist < 5:
                    val = 1.0 - (dist / 5.0)
                    c = WHITE_SOFT if dist < 1 else color
                    if 0 <= idx < N: pixels[idx] = (int(c[0]*val), int(c[1]*val), int(c[2]*val))

        elif t < 0.85:
            # FASE 3: ¡Las luces se posan encima del Zord! -> ¡DISPARO INMEDIATO DEL RUGIDO!
            if not sound_played:
                threading.Thread(target=play_zord_sound, args=(ranger_name,), daemon=True).start()
                sound_played = True

            prog = (t - 0.65) / 0.20
            pulse = 0.85 + 0.15 * math.sin(prog * math.pi * 6)
            for i in z_target:
                if 0 <= i < N:
                    pixels[i] = (int(color[0] * pulse), int(color[1] * pulse), int(color[2] * pulse))
            for i in r_target:
                if 0 <= i < N:
                    pixels[i] = color

        else:
            # FASE 4: Consolidación del color puro e intenso
            for i in z_target:
                if 0 <= i < N: pixels[i] = color
            for i in r_target:
                if 0 <= i < N: pixels[i] = color

        send_frame(pixels)
        time.sleep(1.0 / fps)

    if current_effect_token == token:
        for i in z_target:
            LIT_STATE[i] = color
        for i in r_target:
            LIT_STATE[i] = color
        update_persistent_frame()
        print(f"✨ [PERSISTENCIA] Zord {ranger_name} invocado y encendido permanentemente.", flush=True)

# ========= EFECTO MEGAZORD (ACTIVADO TRAS LOS 5 ZORDS) =========
def run_megazord_effect(token):
    global current_effect_token
    print("🤖 [MEGAZORD] ¡¡INICIANDO GRAN SECUENCIA MEGAZORD EN LA ESTANTERÍA!!", flush=True)

    # Disparar audio local megazord_r.wav
    threading.Thread(target=play_zord_sound, args=("MEGAZORD",), daemon=True).start()

    rectangles = [
        INDEX.get("B_L", []) + INDEX.get("B_T", []) + INDEX.get("B_R", []),       # Rectángulo 4 (Abajo)
        INDEX.get("M_L", []) + INDEX.get("M_T", []) + INDEX.get("M_R", []),       # Rectángulo 3 (Medio)
        INDEX.get("T_L", []) + INDEX.get("T_T", []) + INDEX.get("T_R", []),       # Rectángulo 2 (Arriba)
        INDEX.get("Z1_L", []) + INDEX.get("Z1_T", []) + INDEX.get("Z1_R", []),    # Rectángulo 1 (Zords)
    ]
    special_leds = INDEX.get("Z_FIRE", []) + INDEX.get("Z0_Special", [])

    RANGERS_5_COLORS = [
        (255, 0, 0),      # Rojo
        (0, 80, 255),     # Azul
        (255, 180, 0),    # Amarillo
        (255, 15, 140),   # Rosa
        (160, 0, 255),    # Negro / Púrpura
    ]

    WHITE_FLASH = (255, 255, 255)

    fps = 30
    duration = 54.0  # Duración alineada con megazord_r.wav (~54s)
    total_frames = int(duration * fps)

    for frame in range(total_frames):
        if current_effect_token != token:
            stop_current_audio()
            return

        t_sec = frame / fps
        pixels = [(0, 0, 0)] * N

        if t_sec < 6.5:
            # =========================================================================
            # FASE 1: (0s - 6.5s) ¡COLUMNAS DORADAS SUBIENDO POR LOS 2 CAJONES DE ARRIBA!
            # Rayos dorados de alta potencia suben continuamente y en sincronía por las
            # columnas de los 2 cajones superiores (Zona 2 Rangers + Zona 1 Zords, donde
            # están todos los juguetes).
            # Ambos cajones (Rangers y Zords) vibran con energía pura y chispas blancas.
            # =========================================================================
            # 1. Columnas doradas continuas subiendo por los 2 cajones superiores a la vez
            head_float = t_sec * 2.5 * 9.0  # Onda continua a través de los 2 cajones (9 leds por cajón)
            GOLD_LIGHT = (255, 210, 20)

            for k in range(len(TOYS_COL_LEFT)):
                dist = (head_float - k) % 9.0
                idx_l = TOYS_COL_LEFT[k]
                idx_r = TOYS_COL_RIGHT[k]
                if dist < 5.0:
                    val = 1.0 - (dist / 5.0)
                    c_spark = WHITE_FLASH if dist < 1.3 else (int(GOLD_LIGHT[0] * val), int(GOLD_LIGHT[1] * val), int(GOLD_LIGHT[2] * val))
                    if 0 <= idx_l < N: pixels[idx_l] = c_spark
                    if 0 <= idx_r < N: pixels[idx_r] = c_spark
                else:
                    # Resplandor dorado cálido de base en las columnas de ambos cajones
                    if 0 <= idx_l < N: pixels[idx_l] = (40, 30, 0)
                    if 0 <= idx_r < N: pixels[idx_r] = (40, 30, 0)

            # 2. Los 5 Zords en la balda superior (Cajón 1) vibran con potencia y chispas blancas
            for r in ["RED", "BLUE", "YELLOW", "PINK", "BLACK"]:
                base_c = COLOR_MAP[r]
                for idx in ZORD_LEDS.get(r, []):
                    if 0 <= idx < N:
                        pixels[idx] = WHITE_FLASH if random.random() < 0.35 else base_c

            # 3. Los 5 Rangers en la balda de abajo (Cajón 2) también brillan radiantes
            for r in ["RED", "BLUE", "YELLOW", "PINK", "BLACK"]:
                base_c = COLOR_MAP[r]
                for idx in RANGER_LEDS.get(r, []):
                    if 0 <= idx < N:
                        pixels[idx] = WHITE_FLASH if random.random() < 0.20 else base_c

            # 4. Zona especial / fuego parpadeando con destellos dorados y rojos
            for idx in special_leds:
                if 0 <= idx < N:
                    pixels[idx] = (255, 200, 0) if (frame % 4 < 2) else (255, 40, 0)

        elif t_sec < 15.0:
            # =========================================================================
            # FASE 2: (6.5s - 15s) ¡TRANSFERENCIA DE PLASMA & CONEXIÓN TOTAL!
            # Cometas de energía bajan a toda velocidad por las columnas de los 2 cajones superiores.
            # Zords y Rangers brillan al 100% de color mientras la energía viaja.
            # =========================================================================
            head_down = (t_sec - 6.5) * 2.5 * 9.0
            for k in range(len(TOYS_COL_LEFT)):
                dist = (k - head_down) % 9.0
                if dist < 5.0:
                    val = 1.0 - (dist / 5.0)
                    c_comet = (int(255 * val), int(220 * val), int(140 * val))
                    if 0 <= TOYS_COL_LEFT[k] < N: pixels[TOYS_COL_LEFT[k]] = c_comet
                    if 0 <= TOYS_COL_RIGHT[k] < N: pixels[TOYS_COL_RIGHT[k]] = c_comet
                else:
                    if 0 <= TOYS_COL_LEFT[k] < N: pixels[TOYS_COL_LEFT[k]] = (30, 20, 0)
                    if 0 <= TOYS_COL_RIGHT[k] < N: pixels[TOYS_COL_RIGHT[k]] = (30, 20, 0)

            # Zords y Rangers fijados a plena intensidad con chisporroteo eléctrico
            for r in ["RED", "BLUE", "YELLOW", "PINK", "BLACK"]:
                c = COLOR_MAP[r]
                for idx in ZORD_LEDS.get(r, []):
                    if 0 <= idx < N:
                        pixels[idx] = WHITE_FLASH if random.random() < 0.15 else c
                for idx in RANGER_LEDS.get(r, []):
                    if 0 <= idx < N:
                        pixels[idx] = WHITE_FLASH if random.random() < 0.15 else c

            # Pulsos en los cubos inferiores
            pulse_mid = 0.5 + 0.5 * math.sin((t_sec - 6.5) * math.pi * 3)
            for led_i in rectangles[0] + rectangles[1]:
                if 0 <= led_i < N:
                    pixels[led_i] = (int(40 * pulse_mid), int(20 * pulse_mid), int(80 * pulse_mid))

        elif t_sec < 32.0:
            # =========================================================================
            # FASE 3: (15s - 32s) ¡GRAN ENSAMBLAJE MEGAZORD (TRANSFORMACIÓN)!
            # Los 4 cajones alternan secuencias cromáticas rápidas de los 5 colores Rangers
            # con chisporroteo blanco de alta energía.
            # =========================================================================
            cycle_step = int((t_sec - 15.0) * 2.5)
            for rect_idx, rect_leds in enumerate(rectangles):
                base_col = RANGERS_5_COLORS[(cycle_step + rect_idx) % len(RANGERS_5_COLORS)]
                for led_i in rect_leds:
                    if 0 <= led_i < N:
                        r_rnd = random.random()
                        if r_rnd < 0.15:
                            pixels[led_i] = WHITE_FLASH
                        elif r_rnd < 0.35:
                            pixels[led_i] = (min(255, int(base_col[0] * 0.5 + 128)),
                                             min(255, int(base_col[1] * 0.5 + 128)),
                                             min(255, int(base_col[2] * 0.5 + 128)))
                        else:
                            pixels[led_i] = base_col

            # Los 5 Zords en la balda superior permanecen como faros de potencia pura
            for r in ["RED", "BLUE", "YELLOW", "PINK", "BLACK"]:
                for idx in ZORD_LEDS.get(r, []):
                    if 0 <= idx < N: pixels[idx] = COLOR_MAP[r]

        elif t_sec < 48.0:
            # =========================================================================
            # FASE 4: (32s - 48s) ¡ESPADA DE PODER Y COMBATE DEFINITIVO!
            # Destellos dorados y fuego en special_leds, tajos de luz en columnas laterales.
            # =========================================================================
            strobe_gold = (int(t_sec * 8) % 2 == 0)
            gold_color = (255, 210, 20) if strobe_gold else (255, 50, 0)
            for led_i in special_leds:
                if 0 <= led_i < N: pixels[led_i] = gold_color

            # Tajo de espada que barre las columnas a gran velocidad
            sword_sweep = int((t_sec * 12) % len(COL_LEFT)) if COL_LEFT else 0
            for k in range(len(COL_LEFT)):
                if abs(k - sword_sweep) < 4:
                    if 0 <= COL_LEFT[k] < N: pixels[COL_LEFT[k]] = WHITE_FLASH
                    if 0 <= COL_RIGHT[k] < N: pixels[COL_RIGHT[k]] = WHITE_FLASH
                else:
                    if 0 <= COL_LEFT[k] < N: pixels[COL_LEFT[k]] = (60, 0, 0)
                    if 0 <= COL_RIGHT[k] < N: pixels[COL_RIGHT[k]] = (60, 0, 0)

            # Los 5 Zords y Rangers encendidos en sus colores vivos
            for r in ["RED", "BLUE", "YELLOW", "PINK", "BLACK"]:
                c = COLOR_MAP[r]
                for idx in ZORD_LEDS.get(r, []) + RANGER_LEDS.get(r, []):
                    if 0 <= idx < N: pixels[idx] = c

        else:
            # =========================================================================
            # FASE 5: (48s - 54s) ¡VICTORIA TRIUNFAL Y CONSOLIDACIÓN!
            # Asentamiento glorioso en colores permanentes para la estantería.
            # =========================================================================
            for r in ["RED", "BLUE", "YELLOW", "PINK", "BLACK"]:
                c = COLOR_MAP[r]
                for idx in ZORD_LEDS.get(r, []) + RANGER_LEDS.get(r, []):
                    if 0 <= idx < N: pixels[idx] = c
            for idx in COL_LEFT + COL_RIGHT:
                if 0 <= idx < N: pixels[idx] = (30, 10, 0)

        send_frame(pixels)
        time.sleep(1.0 / fps)

    if current_effect_token == token:
        # Dejar encendidos de forma permanente los 5 Zords y Rangers
        for r in ["RED", "BLUE", "YELLOW", "PINK", "BLACK"]:
            c = COLOR_MAP[r]
            for idx in ZORD_LEDS.get(r, []) + RANGER_LEDS.get(r, []):
                LIT_STATE[idx] = c
        update_persistent_frame()
        print("🏆 [MEGAZORD] Secuencia Megazord finalizada. Zords y Rangers encendidos en la estantería.", flush=True)

# ========= EFECTO 3: DE PREMIO OSCAR - INTRO GO GO POWER RANGERS =========
intro_event_active = False

def run_gogo_intro_effect(token):
    global current_effect_token, intro_event_active
    print("🏆 [SHOW OSCAR] ¡Iniciando gran espectáculo GO GO POWER RANGERS (Chisporroteo Eléctrico)!", flush=True)
    
    LIT_STATE.clear()
    update_persistent_frame()
    intro_event_active = True

    # 4 Rectángulos / Cubos completos de la estantería (Zona 4 a Zona 1)
    rectangles = [
        INDEX.get("B_L", []) + INDEX.get("B_T", []) + INDEX.get("B_R", []),       # Rectángulo 4 (Abajo)
        INDEX.get("M_L", []) + INDEX.get("M_T", []) + INDEX.get("M_R", []),       # Rectángulo 3 (Medio)
        INDEX.get("T_L", []) + INDEX.get("T_T", []) + INDEX.get("T_R", []),       # Rectángulo 2 (Arriba)
        INDEX.get("Z1_L", []) + INDEX.get("Z1_T", []) + INDEX.get("Z1_R", []),    # Rectángulo 1 (Zords)
    ]

    RANGERS_6_COLORS = [
        (255, 0, 0),      # Rojo Intenso
        (0, 80, 255),     # Azul Intenso
        (255, 180, 0),    # Amarillo Intenso
        (255, 15, 140),   # Rosa Intenso
        (0, 255, 60),     # Verde Intenso
        (160, 0, 255),    # Negro / Púrpura Intenso
    ]

    WHITE_SPARK = (255, 255, 255)  # Blanco puro al máximo brillo

    def get_random_4_colors(prev_colors=None):
        """Devuelve 4 colores distintos aleatorios, cambiando respecto al paso anterior."""
        for _ in range(10):
            sample = random.sample(RANGERS_6_COLORS, 4)
            if prev_colors is None or any(sample[i] != prev_colors[i] for i in range(4)):
                return sample
        return random.sample(RANGERS_6_COLORS, 4)

    fps = 30
    frame_count = 0
    step_duration_frames = int(0.50 * fps)  # 0.50 segundos por bloque
    active_4_colors = get_random_4_colors()

    while intro_event_active and (current_effect_token == token):
        # Cada cambio de compás, asignar un nuevo reparto completamente aleatorio de colores a los 4 cajones
        if frame_count > 0 and (frame_count % step_duration_frames == 0):
            active_4_colors = get_random_4_colors(active_4_colors)

        pixels = [(0, 0, 0)] * N

        # Ráfaga inicial enérgica en el golpe de compás
        is_step_impact = (frame_count % step_duration_frames < 3)

        # Pintar cada rectángulo de su color con chisporroteo eléctrico aumentado (blanco puro + color saturado)
        for rect_idx, rect_leds in enumerate(rectangles):
            base_col = active_4_colors[rect_idx]
            for led_i in rect_leds:
                if 0 <= led_i < N:
                    if is_step_impact and random.random() < 0.45:
                        # Ráfaga de impacto con blanco puro
                        pixels[led_i] = WHITE_SPARK
                    else:
                        r_val = random.random()
                        if r_val < 0.18:
                            # Chispa de relámpago en blanco puro de máxima intensidad
                            pixels[led_i] = WHITE_SPARK
                        elif r_val < 0.35:
                            # Chispa hiper-intensa aclarada fuertemente hacia blanco (núcleo de plasma)
                            pixels[led_i] = (
                                min(255, int(base_col[0] * 0.45 + 140)),
                                min(255, int(base_col[1] * 0.45 + 140)),
                                min(255, int(base_col[2] * 0.45 + 140))
                            )
                        elif r_val < 0.65:
                            # Color puro de la moneda al 100% de potencia
                            pixels[led_i] = base_col
                        else:
                            # Fondo vibrante de energía fluctuante
                            v = random.uniform(0.70, 0.95)
                            pixels[led_i] = (
                                int(base_col[0] * v),
                                int(base_col[1] * v),
                                int(base_col[2] * v)
                            )

        # Ráfaga y chispas en la zona especial / fuego
        special_leds = INDEX.get("Z_FIRE", []) + INDEX.get("Z0_Special", [])
        flash_color = active_4_colors[frame_count % 4]
        for led_i in special_leds:
            if 0 <= led_i < N:
                if random.random() < 0.35:
                    pixels[led_i] = WHITE_SPARK
                else:
                    pixels[led_i] = flash_color

        send_frame(pixels)
        time.sleep(1.0 / fps)

        frame_count += 1

    # --- FIN DE LA MÚSICA (Recibido INTRO_STOP) -> Destello de impacto y Apagón ---
    if current_effect_token == token:
        # Cierre estroboscópico deslumbrante (0.2s)
        for flash in range(4):
            f_pixels = [WHITE_SOFT if (flash % 2 == 0) else (255, 0, 0)] * N
            send_frame(f_pixels)
            time.sleep(0.05)

        LIT_STATE.clear()
        update_persistent_frame()
        print("🎬 [SHOW OSCAR] Canción terminada. Estantería en Apagón Total.", flush=True)

# ========= BUCLE PRINCIPAL SERVIDOR UDP =========
def main():
    global current_effect_token, intro_event_active
    print("==================================================")
    print("   POWER MORPHER UDP SERVER (Efectos Mágicos)     ")
    print(f"   Escuchando en {UDP_HOST}:{UDP_PORT}")
    print("==================================================")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        sock.bind((UDP_HOST, UDP_PORT))
    except Exception as e:
        print(f"❌ Error al vincular puerto UDP {UDP_PORT}: {e}", flush=True)
        sys.exit(1)

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            raw_msg = data.decode("utf-8").strip()
            msg = raw_msg.upper()
            print(f"\n📩 [UDP RECIBIDO] desde {addr}: '{raw_msg}'", flush=True)

            if ":" in msg:
                cmd_type, ranger_name = msg.split(":", 1)
                
                if cmd_type in ["INTRO_START", "INTRO"]:
                    current_effect_token += 1
                    tok = current_effect_token
                    t = threading.Thread(target=run_gogo_intro_effect, args=(tok,), daemon=True)
                    t.start()
                elif cmd_type == "INTRO_STOP":
                    intro_event_active = False
                    stop_current_audio()
                    LIT_STATE.clear()
                    update_persistent_frame()
                elif cmd_type == "MEGAZORD" or ranger_name == "MEGAZORD":
                    current_effect_token += 1
                    tok = current_effect_token
                    t = threading.Thread(target=run_megazord_effect, args=(tok,), daemon=True)
                    t.start()
                else:
                    current_effect_token += 1
                    tok = current_effect_token
                    if cmd_type == "MORPH_INTRO":
                        t = threading.Thread(target=run_morph_intro_effect, args=(tok,), daemon=True)
                        t.start()
                    elif cmd_type == "MORPH":
                        t = threading.Thread(target=run_morph_effect, args=(ranger_name, tok), daemon=True)
                        t.start()
                    elif cmd_type == "ZORD":
                        t = threading.Thread(target=run_zord_effect, args=(ranger_name, tok), daemon=True)
                        t.start()

            elif msg in ["INTRO_START", "INTRO"]:
                current_effect_token += 1
                tok = current_effect_token
                t = threading.Thread(target=run_gogo_intro_effect, args=(tok,), daemon=True)
                t.start()
            elif msg == "MEGAZORD":
                current_effect_token += 1
                tok = current_effect_token
                t = threading.Thread(target=run_megazord_effect, args=(tok,), daemon=True)
                t.start()
            elif msg in ["INTRO_STOP", "STOP"]:
                intro_event_active = False
                stop_current_audio()
                LIT_STATE.clear()
                update_persistent_frame()
            elif msg in ["CLEAR", "OFF", "APAGAR"]:
                current_effect_token += 1
                intro_event_active = False
                stop_current_audio()
                LIT_STATE.clear()
                update_persistent_frame()
                print("🧹 [ESTANTERÍA] Apagón total ordenado.", flush=True)

        except KeyboardInterrupt:
            print("\n👋 Cerrando servidor Power Morpher UDP.", flush=True)
            break
        except Exception as e:
            print(f"❌ Error UDP loop: {e}", flush=True)
            time.sleep(0.5)

if __name__ == "__main__":
    main()
