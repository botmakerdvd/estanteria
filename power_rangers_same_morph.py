#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# power.py
# VERSIÓN FINAL SYNC (RUTA CORREGIDA):
# - Ruta de video ajustada a: /home/pi/251121/power.mp4
# - Sincronización robusta con MPV.

import time
import math
import random
import sys
import os
import socket
import json
import subprocess
import atexit
import requests
from itertools import chain

# --- IMPORTACIÓN SEGURA ---
try:
    from layout import *
    # Comprobamos que existan las listas, si no las creamos vacías o por defecto
    if "Z1_T" not in INDEX: INDEX["Z1_T"] = list(range(105, 123))
    if "T_T" not in INDEX:  INDEX["T_T"]  = list(range(69, 87))
    if "Z1_R" not in INDEX: INDEX["Z1_R"] = []
    if "Z1_L" not in INDEX: INDEX["Z1_L"] = []
    if "T_R" not in INDEX:  INDEX["T_R"]  = []
    if "T_L" not in INDEX:  INDEX["T_L"]  = []
except ImportError:
    print("[ERROR] Falta 'layout.py'.")
    sys.exit(1)

try:
    from rf_control import RFManager
    HAS_RF = True
except ImportError:
    HAS_RF = False

# ========= CONFIGURACIÓN =========
HOST = "http://localhost:8090"
PRIORITY = 50
ORIGIN = "PowerRangersUltimate"

# VIDEO CONFIG (RUTA CORREGIDA)
VIDEO_FILE = "/home/pi/251121/power.mp4"  # <--- AQUÍ ESTABA EL FALLO
AUDIO_DEVICE = "alsa/hdmi:CARD=vc4hdmi,DEV=0"
SOCK_PATH = "/tmp/mpv_rangers.sock"
MPV_LOG = "/tmp/mpv_rangers.log"

# COLORES
C_OFF    = (0, 0, 0)
C_FINAL_AMBIENT = (120, 120, 120) 

C_RED    = (255, 0, 0)
C_YELLOW = (255, 180, 0)
C_BLACK  = (60, 0, 100)   
C_BLUE   = (0, 0, 255)
C_PINK   = (255, 0, 110)
C_WHITE  = (200, 220, 255)
C_GREEN  = (0, 255, 0)
C_RITA   = (255, 20, 0)    
C_ZEDD   = (180, 0, 255)   
C_ZORDON = (0, 220, 255)   
C_ALFA   = (255, 50, 50)
C_GOLD   = (255, 160, 20)
C_ALARM_A = (255, 0, 0)
C_ALARM_B = (255, 200, 0)

# ========= MAPEO DE ZONAS =========

# 1. ZONA 1 (ARRIBA)
Z1_STRIP = list(reversed(INDEX["Z1_T"]))
Z1_SIDE_R = INDEX.get("Z1_R", [])

LEDS_VILLAINS    = Z1_STRIP[0:5]
LEDS_VILLAINS_FULL = LEDS_VILLAINS + Z1_SIDE_R

LEDS_ZORD_YELLOW = Z1_STRIP[5:7]
LEDS_ZORD_BLACK  = [Z1_STRIP[7]]
LEDS_ZORD_RED    = [Z1_STRIP[8]]
LEDS_ZORD_PINK   = Z1_STRIP[9:11]
LEDS_ZORD_BLUE   = Z1_STRIP[11:13]
LEDS_ZORD_WHITE  = Z1_STRIP[13:18]

# 2. ZONA 2 (MEDIO)
Z2_STRIP = list(reversed(INDEX["T_T"]))

POS_R_RED    = Z2_STRIP[4:6]
POS_R_YELLOW = Z2_STRIP[6:8]
POS_R_BLACK  = Z2_STRIP[8:10]
POS_R_BLUE   = Z2_STRIP[9:11]  
POS_R_PINK   = Z2_STRIP[11:13]
POS_R_WHITE  = Z2_STRIP[13:15]

LEDS_ZORDON  = Z2_STRIP[7:11] 
LEDS_ALFA    = LEDS_ZORDON 

# 3. COLUMNAS
COL_RIGHT_UP = INDEX.get("T_R", []) + INDEX.get("Z1_R", [])
COL_LEFT_UP  = INDEX.get("T_L", []) + INDEX.get("Z1_L", [])

# 4. LATERALES GENERALES
ALL_SIDES = []
for k, v in INDEX.items():
    if "_L" in k or "_R" in k: 
        ALL_SIDES.extend(v)

# TIMELINE
T_START_ALARM     = 14.12
T_START_ALFA      = 16.52
T_START_TELEPORT  = 19.60
T_START_PREMORPH  = 24.28
T_START_RED       = 28.08
T_START_YELLOW    = 34.60
T_START_BLACK     = 40.36
T_START_BLUE      = 46.20
T_START_PINK      = 52.24
T_START_WHITE     = 58.52
T_START_MEGAZORD  = 67.52
T_START_FINAL     = 109.72

RANGERS_TIMELINE = [
    (T_START_RED,    "RED",    POS_R_RED,    C_RED,    LEDS_ZORD_RED),
    (T_START_YELLOW, "YELLOW", POS_R_YELLOW, C_YELLOW, LEDS_ZORD_YELLOW),
    (T_START_BLACK,  "BLACK",  POS_R_BLACK,  C_BLACK,  LEDS_ZORD_BLACK),
    (T_START_BLUE,   "BLUE",   POS_R_BLUE,   C_BLUE,   LEDS_ZORD_BLUE),
    (T_START_PINK,   "PINK",   POS_R_PINK,   C_PINK,   LEDS_ZORD_PINK),
    (T_START_WHITE,  "WHITE",  POS_R_WHITE,  C_WHITE,  LEDS_ZORD_WHITE),
]

# ========= GESTIÓN MPV =========
mpv_proc = None
ipc_sock = None

def cleanup_mpv():
    try:
        if ipc_sock: ipc_sock.close()
    except: pass
    try:
        if mpv_proc: mpv_proc.terminate()
    except: pass
    try:
        send_frame(frame_fill(C_OFF))
    except: pass

atexit.register(cleanup_mpv)

def start_mpv(video_path):
    global mpv_proc
    if os.path.exists(SOCK_PATH):
        try: os.remove(SOCK_PATH)
        except: pass
        
    cmd = [
        "mpv", video_path,
        "--fs", "--no-osc", "--keep-open=no",
        f"--input-ipc-server={SOCK_PATH}",
        "--gpu-context=drm",
        "--ao=alsa", "--audio-samplerate=48000",
        "--volume=100", "--mute=no",
    ]
    if AUDIO_DEVICE:
        cmd.append(f"--audio-device={AUDIO_DEVICE}")
        
    # Abrimos logs para ver si falla MPV
    logf = open(MPV_LOG, "w")
    mpv_proc = subprocess.Popen(cmd, stdout=logf, stderr=logf)

def connect_ipc(timeout=10.0):
    global ipc_sock
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(SOCK_PATH): break
        time.sleep(0.1)
    try:
        ipc_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        ipc_sock.connect(SOCK_PATH)
        return True
    except: return False

def get_video_time():
    if not ipc_sock: return 0.0
    req = json.dumps({"command": ["get_property", "time-pos"], "request_id": 1}) + "\n"
    try:
        ipc_sock.sendall(req.encode("utf-8"))
        ipc_sock.settimeout(0.1)
        data = ipc_sock.recv(4096).decode("utf-8")
        for line in data.split('\n'):
            if not line: continue
            msg = json.loads(line)
            if msg.get("error") == "success" and "data" in msg:
                # A veces mpv devuelve None al arrancar
                val = msg["data"]
                return float(val) if val is not None else 0.0
    except: pass
    return 0.0

# ========= UTILIDADES GRÁFICAS =========
ACTIVE_ZORDS = {} 

def send_frame(pixels, duration=-1):
    flat = []
    for r, g, b in pixels:
        flat.extend([int(r), int(g), int(b)])
    try:
        requests.post(f"{HOST}/json-rpc", 
                      json={"command":"color", "color":flat, "priority":PRIORITY, "origin":ORIGIN, "duration":duration}, 
                      timeout=0.2)
    except: pass

def frame_fill(color): return [color] * N

def get_base_frame():
    px = [C_OFF] * N
    for idx, col in ACTIVE_ZORDS.items(): px[idx] = col
    return px

def set_color(px, i, c): 
    if 0 <= i < N: px[i] = c

def add_color(px, i, c):
    if 0 <= i < N:
        r,g,b = px[i]
        px[i] = (min(255, r+c[0]), min(255, g+c[1]), min(255, b+c[2]))

def scale(c, k): return (int(c[0]*k), int(c[1]*k), int(c[2]*k))
def mix(c1, c2, t): 
    return (int(c1[0]+(c2[0]-c1[0])*t), int(c1[1]+(c2[1]-c1[1])*t), int(c1[2]+(c2[2]-c1[2])*t))

# ========= EFECTOS BÁSICOS =========
def effect_climb(base_col, duration):
    t0 = time.time()
    while (time.time() - t0) < duration:
        t_norm = (time.time() - t0) / duration
        phase = (t_norm * 3) % 1.0
        px = get_base_frame()
        h_active = phase * 4
        zones = [INDEX["B_L"]+INDEX["B_R"]+INDEX["B_T"], 
                 INDEX["M_L"]+INDEX["M_R"]+INDEX["M_T"], 
                 INDEX["T_L"]+INDEX["T_R"]+INDEX["T_T"], 
                 INDEX["Z1_L"]+INDEX["Z1_R"]+INDEX["Z1_T"]]
        for z_idx, zone in enumerate(zones):
            dist = abs(z_idx - h_active)
            if dist < 1.2:
                k = 1.0 - (dist/1.2)
                for i in zone: 
                    if i not in ACTIVE_ZORDS: add_color(px, i, scale(base_col, k))
        send_frame(px); time.sleep(0.05)

def effect_lightning(base_col, duration):
    t0 = time.time()
    while (time.time() - t0) < duration:
        px = get_base_frame()
        for i in range(N):
            if i not in ACTIVE_ZORDS and random.random() < 0.1:
                add_color(px, i, scale(base_col, 0.3))
        for _ in range(5):
            pos = random.randint(0, N-1)
            if pos not in ACTIVE_ZORDS:
                set_color(px, pos, C_WHITE)
                if pos+1 < N: add_color(px, pos+1, scale(base_col, 0.7))
        send_frame(px); time.sleep(0.04)

def effect_energy_implosion(ranger_leds, color, duration):
    t0 = time.time()
    while (time.time() - t0) < duration:
        t_norm = (time.time() - t0) / duration
        px = get_base_frame()
        ranger_bright = scale(color, 0.2 + 0.8 * (t_norm**2))
        for i in ranger_leds: set_color(px, i, ranger_bright)
        density = 0.2 * (1.0 - t_norm)
        for i in range(N):
            if i not in ACTIVE_ZORDS and i not in ranger_leds:
                if random.random() < density:
                    add_color(px, i, scale(C_WHITE, 0.6))
        send_frame(px); time.sleep(0.05)

def effect_snake_transfer(start_leds, end_leds, color, duration):
    t0 = time.time()
    while (time.time() - t0) < duration:
        t_norm = (time.time() - t0) / duration
        px = get_base_frame()
        if t_norm < 0.3:
            for i in start_leds: set_color(px, i, color)
        if t_norm > 0.1 and t_norm < 0.9:
            climb_t = (t_norm - 0.1) / 0.7
            for col_strip in [COL_RIGHT_UP, COL_LEFT_UP]:
                strip_len = len(col_strip)
                head_pos = int(climb_t * strip_len)
                for k in range(5):
                    idx = head_pos - k
                    if 0 <= idx < strip_len:
                        intensity = 1.0 - (k/5.0)
                        led_idx = col_strip[idx]
                        add_color(px, led_idx, scale(color, intensity))
        if t_norm > 0.8:
            if int(time.time()*20) % 2 == 0:
                for i in end_leds: set_color(px, i, C_WHITE)
            else:
                for i in end_leds: set_color(px, i, color)
        send_frame(px); time.sleep(0.03)

# ========= ESCENAS =========
def scene_alarm_emergency(duration):
    print(">>> ALARMA GENERAL")
    t0 = time.time()
    while (time.time() - t0) < duration:
        state = int(time.time() * 4) % 2
        col = C_ALARM_A if state == 0 else C_ALARM_B
        px = [C_OFF] * N
        for i in range(N): px[i] = scale(col, 0.8)
        send_frame(px); time.sleep(0.05)

def scene_teleport(duration):
    print(">>> TELETRANSPORTE")
    t0 = time.time()
    while (time.time() - t0) < duration:
        px = get_base_frame()
        for _ in range(10):
            i = random.randint(0, N-1)
            if random.random() > 0.5: px[i] = C_WHITE
            else: px[i] = C_BLUE
        send_frame(px); time.sleep(0.04)

def scene_villains(duration):
    print(">>> Villanos")
    t0 = time.time()
    while (time.time() - t0) < duration:
        t = time.time() - t0
        k = 0.2 + 0.8 * ((math.sin(t*3)+1)/2)
        col = mix(C_RITA, C_ZEDD, 0.5+0.5*math.sin(t))
        px = get_base_frame()
        for i in LEDS_VILLAINS_FULL: set_color(px, i, scale(col, k))
        send_frame(px); time.sleep(0.05)

def scene_alfa_panic(duration):
    print(">>> Alfa 5")
    t0 = time.time()
    while (time.time() - t0) < duration:
        px = get_base_frame()
        state = int(time.time() * 18) % 2
        alfa_color = C_ALFA if state == 0 else C_WHITE
        for i in LEDS_ALFA: set_color(px, i, alfa_color)
        send_frame(px); time.sleep(0.05)

def scene_zordon_premorph(duration):
    print(">>> Zordon")
    t0 = time.time()
    while (time.time() - t0) < duration:
        px = get_base_frame()
        z_int = random.uniform(0.6, 1.0)
        for i in LEDS_ZORDON: set_color(px, i, scale(C_ZORDON, z_int))
        for i in ALL_SIDES: set_color(px, i, scale(C_ZORDON, 0.1))
        send_frame(px); time.sleep(0.04)

# ========= MEGAZORD MULTI-FASE =========
def scene_megazord_complex(remaining_time):
    """Secuencia sincronizada con 12_megathunderzord.mpg"""
    t_start = time.time()
    time_limit = remaining_time
    ASSEMBLY_COLORS = [C_YELLOW, C_BLACK, C_BLUE, C_PINK, C_WHITE]

    while True:
        elapsed = time.time() - t_start
        if elapsed >= time_limit: break
        px = get_base_frame() 
        
        if elapsed < 8.0:
            for i in LEDS_ZORD_RED: set_color(px, i, C_RED)
            scan_pos = int((elapsed * 15) % len(Z1_STRIP))
            set_color(px, Z1_STRIP[scan_pos], C_GOLD)
        elif elapsed < 18.0:
            for _ in range(5):
                rand_zord_idx = random.choice(list(ACTIVE_ZORDS.keys()))
                rand_col = random.choice(ASSEMBLY_COLORS)
                set_color(px, rand_zord_idx, rand_col)
            for i in ALL_SIDES:
                if random.random() < 0.2: set_color(px, i, scale(C_WHITE, 0.5))
        elif elapsed < 28.0:
            for _ in range(3):
                pos = random.randint(0, N-1)
                if pos not in ACTIVE_ZORDS:
                    set_color(px, pos, C_WHITE)
                    if pos+1 < N: add_color(px, pos+1, C_BLUE)
        elif elapsed < 35.0:
            blink = (math.sin(elapsed*10)+1)/2
            for _, r_leds, r_col, _, _ in RANGERS_TIMELINE:
                for i in r_leds: set_color(px, i, r_col)
            for idx in ACTIVE_ZORDS.keys():
                set_color(px, idx, C_GOLD)
        else:
            cycle = (elapsed - 35.0) * 2
            h_fill = (cycle % 1.0) * 4
            zones = [INDEX["B_L"]+INDEX["B_R"]+INDEX["B_T"], 
                     INDEX["M_L"]+INDEX["M_R"]+INDEX["M_T"], 
                     INDEX["T_L"]+INDEX["T_R"]+INDEX["T_T"], 
                     INDEX["Z1_L"]+INDEX["Z1_R"]+INDEX["Z1_T"]]
            for z_idx, zone in enumerate(zones):
                if z_idx < h_fill:
                    for i in zone: 
                        if i not in ACTIVE_ZORDS: set_color(px, i, scale(C_GOLD, 0.3))
                if abs(z_idx - h_fill) < 0.5:
                    for i in zone: 
                        if i not in ACTIVE_ZORDS: set_color(px, i, C_WHITE)
        send_frame(px); time.sleep(0.04)

# ========= MAIN =========
def run_show():
    rf = None
    if HAS_RF: rf = RFManager()
    
    print(f">>> Iniciando Video: {VIDEO_FILE}")
    if not os.path.exists(VIDEO_FILE):
        print("[ERROR FATAL] No encuentro el archivo de video.")
        return

    start_mpv(VIDEO_FILE)
    if not connect_ipc():
        print("[ERROR] MPV no responde.")
        return

    print(">>> Sincronizando...")
    current_state = "start"
    
    try:
        while True:
            if mpv_proc.poll() is not None: break
            t_video = get_video_time()
            
            if t_video < T_START_ALARM:
                remaining = T_START_ALARM - t_video
                if remaining > 0.1: scene_villains(remaining)
            elif t_video < T_START_ALFA:
                remaining = T_START_ALFA - t_video
                if remaining > 0.1: scene_alarm_emergency(remaining)
            elif t_video < T_START_TELEPORT:
                remaining = T_START_TELEPORT - t_video
                if remaining > 0.1: scene_alfa_panic(remaining)
            elif t_video < T_START_PREMORPH:
                remaining = T_START_PREMORPH - t_video
                if remaining > 0.1: scene_teleport(remaining)
            elif t_video < T_START_RED:
                remaining = T_START_RED - t_video
                if remaining > 0.1: scene_zordon_premorph(remaining)
            elif t_video < T_START_MEGAZORD:
                next_ranger_idx = -1
                for idx, (start_t, _, _, _, _) in enumerate(RANGERS_TIMELINE):
                    if t_video >= start_t: next_ranger_idx = idx
                    else: break
                
                if next_ranger_idx >= 0:
                    r_start, r_name, r_leds, r_col, z_leds = RANGERS_TIMELINE[next_ranger_idx]
                    if next_ranger_idx < len(RANGERS_TIMELINE) - 1:
                        r_end = RANGERS_TIMELINE[next_ranger_idx+1][0]
                    else:
                        r_end = T_START_MEGAZORD
                    duration_total = r_end - r_start
                    elapsed = t_video - r_start
                    if elapsed < duration_total:
                        state_key = f"ranger_{r_name}"
                        if current_state != state_key:
                            print(f"[{t_video:.1f}] Ranger: {r_name}")
                            current_state = state_key
                            d_implosion = duration_total * 0.35
                            d_climb = duration_total * 0.20
                            d_snake = duration_total * 0.25
                            d_light = duration_total * 0.20
                            effect_energy_implosion(r_leds, r_col, d_implosion)
                            effect_climb(r_col, d_climb)
                            effect_snake_transfer(r_leds, z_leds, r_col, d_snake)
                            effect_lightning(r_col, d_light)
                            for i in z_leds: ACTIVE_ZORDS[i] = r_col
            elif t_video < T_START_FINAL:
                remaining = T_START_FINAL - t_video
                if remaining > 0.1:
                    print(f"[{t_video:.1f}] MEGAZORD SEQUENCE")
                    scene_megazord_complex(remaining)
            else:
                if current_state != "final":
                    print(">>> FINAL FIJO")
                    current_state = "final"
                    FINAL_ZONES = set(ZONE1 + ZONE2)
                    RANGERS_FINAL_POS = {}
                    for _, _, r_leds, r_col, _ in RANGERS_TIMELINE:
                        for i in r_leds: RANGERS_FINAL_POS[i] = r_col
                    for k in range(50):
                        factor = k/50.0
                        px = [C_OFF] * N
                        for i in FINAL_ZONES: px[i] = scale(C_FINAL_AMBIENT, factor)
                        for idx, col in ACTIVE_ZORDS.items(): px[idx] = col
                        for idx, col in RANGERS_FINAL_POS.items(): px[idx] = col
                        send_frame(px); time.sleep(0.05)
                    final_px = [C_OFF] * N
                    for i in FINAL_ZONES: final_px[i] = C_FINAL_AMBIENT
                    for idx, col in ACTIVE_ZORDS.items(): final_px[idx] = col
                    for idx, col in RANGERS_FINAL_POS.items(): final_px[idx] = col
                    while True:
                        if mpv_proc.poll() is not None: break
                        send_frame(final_px)
                        time.sleep(1.0)
                    break

    except KeyboardInterrupt:
        print("\nCancelado.")
    finally:
        if rf: rf.cleanup()
        cleanup_mpv()

if __name__ == "__main__":
    run_show()