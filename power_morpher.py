#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# power_morpher.py
# Servidor UDP para efectos mágicos de iluminación Morpher <-> Estantería Power Rangers

import socket
import time
import math
import random
import threading
import requests
import sys

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
    print(f"⚡ [EFECTO RANGER] Metamorfosis para {ranger_name}...")
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
    duration = 2.8
    total_frames = int(duration * fps)

    for frame in range(total_frames):
        if current_effect_token != token:
            return

        t = frame / total_frames
        pixels = render_base_frame()

        if t < 0.30:
            prog = t / 0.30
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

        elif t < 0.65:
            prog = (t - 0.30) / 0.35
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
            # FASE 3: Llegada e encendido directo en COLOR INTENSO PURO (sin destellos blancos lavadores)
            prog = (t - 0.65) / 0.20
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
        print(f"✨ [PERSISTENCIA] Ranger {ranger_name} activado y encendido permanentemente.")

# ========= EFECTO 2: INVOCACIÓN ZORD (ZORD) =========
def run_zord_effect(ranger_name, token):
    global current_effect_token
    print(f"🐉 [EFECTO ZORD] Invocación para Zord {ranger_name}...")
    color = COLOR_MAP.get(ranger_name, (255, 0, 0))
    z_target = ZORD_LEDS.get(ranger_name, [])
    r_target = RANGER_LEDS.get(ranger_name, [])

    if z_target and Z1_STRIP:
        target_indices_in_strip = [Z1_STRIP.index(i) for i in z_target if i in Z1_STRIP]
        mid_strip_pos = sum(target_indices_in_strip) / len(target_indices_in_strip) if target_indices_in_strip else len(Z1_STRIP) / 2
    else:
        mid_strip_pos = len(Z1_STRIP) / 2 if Z1_STRIP else 0

    dist_left = mid_strip_pos
    dist_right = (len(Z1_STRIP) - 1) - mid_strip_pos if Z1_STRIP else 1

    fps = 30
    duration = 3.0
    total_frames = int(duration * fps)

    for frame in range(total_frames):
        if current_effect_token != token:
            return

        t = frame / total_frames
        pixels = render_base_frame()

        if t < 0.30:
            prog = t / 0.30
            len_l = len(COL_LEFT)
            len_r = len(COL_RIGHT)
            head_l = int(prog * len_l)
            head_r = int(prog * len_r)

            for k in range(len_l):
                dist = head_l - k
                if 0 <= dist < 7:
                    k_val = 1.0 - (dist / 7.0)
                    idx = COL_LEFT[k]
                    c = WHITE_SOFT if dist < 2 else color
                    if 0 <= idx < N: pixels[idx] = (int(c[0]*k_val), int(c[1]*k_val), int(c[2]*k_val))

            for k in range(len_r):
                dist = head_r - k
                if 0 <= dist < 7:
                    k_val = 1.0 - (dist / 7.0)
                    idx = COL_RIGHT[k]
                    c = WHITE_SOFT if dist < 2 else color
                    if 0 <= idx < N: pixels[idx] = (int(c[0]*k_val), int(c[1]*k_val), int(c[2]*k_val))

        elif t < 0.65:
            prog = (t - 0.30) / 0.35
            pos_left = int(prog * dist_left)
            pos_right = (len(Z1_STRIP) - 1) - int(prog * dist_right)

            for k in range(len(Z1_STRIP)):
                if k <= pos_left:
                    idx = Z1_STRIP[k]
                    dist = pos_left - k
                    if dist < 5:
                        val = 1.0 - (dist / 5.0)
                        c = WHITE_SOFT if dist < 1 else color
                        if 0 <= idx < N: pixels[idx] = (int(c[0]*val), int(c[1]*val), int(c[2]*val))

            for k in range(len(Z1_STRIP) - 1, -1, -1):
                if k >= pos_right:
                    idx = Z1_STRIP[k]
                    dist = k - pos_right
                    if dist < 5:
                        val = 1.0 - (dist / 5.0)
                        c = WHITE_SOFT if dist < 1 else color
                        if 0 <= idx < N: pixels[idx] = (int(c[0]*val), int(c[1]*val), int(c[2]*val))

        elif t < 0.85:
            # FASE 3: Colisión e encendido directo en COLOR INTENSO PURO
            prog = (t - 0.65) / 0.20
            pulse = 0.85 + 0.15 * math.sin(prog * math.pi * 6)
            for i in z_target:
                if 0 <= i < N:
                    pixels[i] = (int(color[0] * pulse), int(color[1] * pulse), int(color[2] * pulse))
            for i in r_target:
                if 0 <= i < N:
                    pixels[i] = color

        else:
            # FASE 4: Consolidación de encendido permanente
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
        print(f"✨ [PERSISTENCIA] Zord {ranger_name} invocado y encendido permanentemente.")

# ========= EFECTO 3: DE PREMIO OSCAR - INTRO GO GO POWER RANGERS =========
intro_event_active = False

def run_gogo_intro_effect(token):
    global current_effect_token, intro_event_active
    print("🏆 [SHOW OSCAR] ¡Iniciando gran espectáculo GO GO POWER RANGERS (Rectángulos Puros)!", flush=True)
    
    LIT_STATE.clear()
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
        (220, 240, 255),  # Blanco Intenso
    ]

    fps = 30
    frame_count = 0
    cycle_step = 0
    step_duration_frames = int(0.50 * fps)  # 0.50 segundos por bloque para disfrutar la potencia del color

    while intro_event_active and (current_effect_token == token):
        pixels = [(0, 0, 0)] * N

        # Paleta de 4 colores activos para los 4 rectángulos en este pulso
        color_offset = cycle_step % len(RANGERS_6_COLORS)
        active_4_colors = [
            RANGERS_6_COLORS[(color_offset + 0) % len(RANGERS_6_COLORS)],
            RANGERS_6_COLORS[(color_offset + 1) % len(RANGERS_6_COLORS)],
            RANGERS_6_COLORS[(color_offset + 2) % len(RANGERS_6_COLORS)],
            RANGERS_6_COLORS[(color_offset + 3) % len(RANGERS_6_COLORS)],
        ]

        # Pintar cada rectángulo entero de su color Ranger
        for rect_idx, rect_leds in enumerate(rectangles):
            col = active_4_colors[rect_idx]
            for led_i in rect_leds:
                if 0 <= led_i < N:
                    pixels[led_i] = col

        # Ráfaga sutil en la zona especial / fuego
        special_leds = INDEX.get("Z_FIRE", []) + INDEX.get("Z0_Special", [])
        flash_color = active_4_colors[frame_count % 4]
        for led_i in special_leds:
            if 0 <= led_i < N:
                pixels[led_i] = flash_color

        send_frame(pixels)
        time.sleep(1.0 / fps)

        frame_count += 1
        if frame_count % step_duration_frames == 0:
            cycle_step += 1

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
            elif msg in ["INTRO_STOP", "STOP"]:
                intro_event_active = False
            elif msg in ["CLEAR", "OFF", "APAGAR"]:
                current_effect_token += 1
                intro_event_active = False
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
