#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# power.py
# VERSIÓN FINAL "FIXED MAPPING":
# - Villanos movidos CORRECTAMENTE a Z0_Special (Estante L).
# - Zords se quedan en Z1_T.
# - Sincronización real-time intacta.

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
    # Fallback de seguridad para Zona 0 si layout.py no se actualizó bien
    if "Z0_Special" not in INDEX: 
        # Asumimos que son los siguientes 11 tras los 132 originales
        INDEX["Z0_Special"] = list(range(132, 143))
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

VIDEO_FILE = "/home/pi/251121/power.mp4"
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
C_RITA   = (180, 0, 255)   
C_ZEDD   = (255, 0, 0)     
C_ZORDON = (0, 220, 255)   
C_ALFA   = (255, 50, 50)
C_GOLD   = (255, 160, 20)
C_ALARM_A = (255, 0, 0)
C_ALARM_B = (255, 200, 0)

# ========= MAPEO DE ZONAS (CORREGIDO) =========

# 1. ZONA 0 (VILLANOS - NUEVO ESTANTE)
# Recuperamos los 11 LEDs de la escuadra superior
Z0_STRIP = INDEX["Z0_Special"]
# Rita (Horizontal, primeros 6)
LEDS_RITA = Z0_STRIP[0:11]
# Zedd (Vertical, últimos 5)
LEDS_ZEDD = Z0_STRIP[0:11]
# Grupo completo
LEDS_VILLAINS_FULL = Z0_STRIP

# 2. ZONA 1 (ZORDS)
# Usamos Z1_T tal cual viene de layout
Z1_STRIP = INDEX["Z1_T"]

# Mapeo Zords (Indices 0-based sobre Z1_STRIP)
LEDS_ZORD_RED    = Z1_STRIP[14:18]    
LEDS_ZORD_YELLOW = Z1_STRIP[11:14]     
LEDS_ZORD_PINK   = Z1_STRIP[8:11]   
LEDS_ZORD_BLACK  = Z1_STRIP[8:11]
LEDS_ZORD_BLUE   = Z1_STRIP[5:8]   
LEDS_ZORD_WHITE  = Z1_STRIP[0:5]   

# 3. ZONA 2 (RANGERS)
Z2_STRIP = list(reversed(INDEX["T_T"])) # Contamos desde derecha

POS_R_RED    = Z2_STRIP[0:5]
POS_R_YELLOW = Z2_STRIP[5:8]
POS_R_BLACK  = Z2_STRIP[8:11]
POS_R_BLUE   = Z2_STRIP[11:14]  
POS_R_PINK   = Z2_STRIP[8:11]
POS_R_WHITE  = Z2_STRIP[14:19]

LEDS_ZORDON  = Z2_STRIP[7:11] 
LEDS_ALFA    = LEDS_ZORDON 

# 4. COLUMNAS Y LATERALES
COL_RIGHT_UP = INDEX.get("T_R", []) + INDEX.get("Z1_R", [])
COL_LEFT_UP  = INDEX.get("T_L", []) + INDEX.get("Z1_L", [])
ALL_SIDES = []
for k, v in INDEX.items():
    if "_L" in k or "_R" in k: 
        ALL_SIDES.extend(v)

# TIMELINE
T_RITA_END        = 9.84
T_ZEDD_END        = 14.12
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
T_START_NEED_MZ   = 67.52
T_START_MEGAZORD  = 71.20 
T_START_FINAL     = 113.40

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
    if not ipc_sock: return -1.0
    req = json.dumps({"command": ["get_property", "time-pos"], "request_id": 1}) + "\n"
    try:
        ipc_sock.sendall(req.encode("utf-8"))
        ipc_sock.settimeout(0.1)
        data = ipc_sock.recv(4096).decode("utf-8")
        for line in data.split('\n'):
            if not line: continue
            msg = json.loads(line)
            if msg.get("error") == "success" and "data" in msg:
                val = msg["data"]
                return float(val) if val is not None else 0.0
    except: pass
    return -1.0

# ========= UTILIDADES GRÁFICAS =========
ACTIVE_ZORDS = {} 

def send_frame(pixels, duration=-1):
    flat = []
    for r, g, b in pixels:
        flat.extend([int(r), int(g), int(b)])
    try:
        requests.post(f"{HOST}/json-rpc", 
                      json={"command":"color", "color":flat, "priority":PRIORITY, "origin":ORIGIN, "duration":-1}, 
                      timeout=0.04) 
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

# ========= EFECTOS =========
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
                    add_color(px, i, scale(color, 0.8))
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

# ========= RENDERIZADORES =========

def render_rita(elapsed):
    k = 0.2 + 0.8 * ((math.sin(elapsed*3)+1)/2)
    px = get_base_frame()
    for i in LEDS_RITA: set_color(px, i, scale(C_RITA, k))
    send_frame(px)

def render_zedd(elapsed):
    k = 0.4 + 0.6 * ((math.sin(elapsed*4)+1)/2)
    px = get_base_frame()
    for i in LEDS_ZEDD: set_color(px, i, scale(C_ZEDD, k))
    send_frame(px)

def render_alarm(elapsed):
    state = int(elapsed * 4) % 2
    col = C_ALARM_A if state == 0 else C_ALARM_B
    px = [C_OFF] * N
    for i in range(N): px[i] = scale(col, 0.8)
    send_frame(px)

def render_alfa(elapsed):
    px = get_base_frame()
    state = int(elapsed * 18) % 2
    alfa_color = C_ALFA if state == 0 else C_WHITE
    for i in LEDS_ALFA: set_color(px, i, alfa_color)
    send_frame(px)

def render_teleport(elapsed):
    px = get_base_frame()
    for _ in range(10):
        i = random.randint(0, N-1)
        if random.random() > 0.5: px[i] = C_WHITE
        else: px[i] = C_BLUE
    send_frame(px)

def render_zordon(elapsed):
    px = get_base_frame()
    z_int = random.uniform(0.6, 1.0)
    for i in LEDS_ZORDON: set_color(px, i, scale(C_ZORDON, z_int))
    wave = (elapsed * 8) % 10
    for col_list in [INDEX["Z1_L"], INDEX["Z1_R"], INDEX["T_L"], INDEX["T_R"]]:
         L = len(col_list)
         for idx, led in enumerate(col_list):
             dist = abs((L - 1 - idx) - wave)
             if dist < 2: add_color(px, led, scale(C_ZORDON, 0.5))
    send_frame(px)

def render_call_megazord(elapsed):
    px = get_base_frame()
    blink = int(elapsed * 15) % 2
    z_pulse = (math.sin(elapsed*20) + 1) / 2
    for i in LEDS_ZORDON: set_color(px, i, scale(C_ZORDON, 0.5 + 0.5*z_pulse))
    for idx, col in ACTIVE_ZORDS.items():
        if blink == 0: set_color(px, idx, C_WHITE)
        else: set_color(px, idx, col)
    send_frame(px)

def render_ranger_morph(elapsed, duration, r_leds, r_col, z_leds):
    px = get_base_frame()
    
    p1 = duration * 0.35
    p2 = p1 + (duration * 0.20)
    p3 = p2 + (duration * 0.25)
    
    if elapsed < p1: 
        t = elapsed / p1
        ranger_bright = scale(r_col, 0.2 + 0.8 * (t**2))
        for i in r_leds: set_color(px, i, ranger_bright)
        density = 0.2 * (1.0 - t)
        for i in range(N):
            if i not in ACTIVE_ZORDS and i not in r_leds:
                if random.random() < density: add_color(px, i, scale(r_col, 0.8))
    
    elif elapsed < p2: 
        t = (elapsed - p1) / (duration * 0.20)
        h_active = (t * 3) % 1.0 * 4
        zones = [INDEX["B_L"]+INDEX["B_R"]+INDEX["B_T"], 
                 INDEX["M_L"]+INDEX["M_R"]+INDEX["M_T"], 
                 INDEX["T_L"]+INDEX["T_R"]+INDEX["T_T"], 
                 INDEX["Z1_L"]+INDEX["Z1_R"]+INDEX["Z1_T"]]
        for z_idx, zone in enumerate(zones):
            if abs(z_idx - h_active) < 1.2:
                k = 1.0 - (abs(z_idx - h_active)/1.2)
                for i in zone: 
                    if i not in ACTIVE_ZORDS: add_color(px, i, scale(r_col, k))
        
    elif elapsed < p3: 
        t = (elapsed - p2) / (duration * 0.25)
        if t < 0.3:
            for i in r_leds: set_color(px, i, r_col)
        if t > 0.1 and t < 0.9:
            climb_t = (t - 0.1) / 0.7
            for col_strip in [COL_RIGHT_UP, COL_LEFT_UP]:
                strip_len = len(col_strip)
                head_pos = int(climb_t * strip_len)
                for k in range(5):
                    idx = head_pos - k
                    if 0 <= idx < strip_len:
                        intensity = 1.0 - (k/5.0)
                        led_idx = col_strip[idx]
                        add_color(px, led_idx, scale(r_col, intensity))
        if t > 0.8:
            if int(elapsed*20) % 2 == 0:
                for i in z_leds: set_color(px, i, C_WHITE)
            else:
                for i in z_leds: set_color(px, i, r_col)

    else: 
        for i in range(N):
            if i not in ACTIVE_ZORDS and random.random() < 0.1:
                add_color(px, i, scale(r_col, 0.3))
        for _ in range(5):
            pos = random.randint(0, N-1)
            if pos not in ACTIVE_ZORDS:
                set_color(px, pos, C_WHITE)
                if pos+1 < N: add_color(px, pos+1, scale(r_col, 0.7))
    
    send_frame(px)

def render_megazord_complex(elapsed):
    px = get_base_frame() 
    ASSEMBLY_COLORS = [C_YELLOW, C_BLACK, C_BLUE, C_PINK, C_WHITE]
    
    ZONES_MAP = [
        (INDEX["B_L"]+INDEX["B_R"]+INDEX["B_T"], C_YELLOW), 
        (INDEX["M_L"]+INDEX["M_R"]+INDEX["M_T"], C_BLUE),   
        (INDEX["T_L"]+INDEX["T_R"]+INDEX["T_T"], C_PINK),   
        (INDEX["Z1_L"]+INDEX["Z1_R"]+INDEX["Z1_T"], C_RED)  
    ]
    
    if elapsed < 8.0:
        for zone_leds, z_col in ZONES_MAP:
            for i in zone_leds:
                set_color(px, i, scale(z_col, 0.15))
        #for i in LEDS_ZORD_RED: set_color(px, i, C_RED)
        scan_pos = int((elapsed * 15) % len(Z1_STRIP))
        set_color(px, Z1_STRIP[scan_pos], C_GOLD)
        
    elif elapsed < 18.0:
        breath = (math.sin(elapsed * 10) + 1) / 2
        for zone_leds, z_col in ZONES_MAP:
            for i in zone_leds:
                set_color(px, i, scale(z_col, 0.2 + 0.6*breath))
        for i in ALL_SIDES:
            if random.random() < 0.15: set_color(px, i, scale(C_WHITE, 0.6))
            
    elif elapsed < 28.0:
        for _ in range(3):
            pos = random.randint(0, N-1)
            #if pos not in ACTIVE_ZORDS:
            set_color(px, pos, C_WHITE)
            if pos+1 < N: add_color(px, pos+1, C_BLUE)
                
    elif elapsed < 35.0:
        for _, _, r_leds, r_col, _ in RANGERS_TIMELINE:
            for i in r_leds: set_color(px, i, r_col)
        for idx in ACTIVE_ZORDS.keys():
            set_color(px, idx, C_GOLD)
            
    else:
        cycle = (elapsed - 35.0) * 2
        h_fill = (cycle % 1.0) * 4
        zones_list = [z[0] for z in ZONES_MAP]
        for z_idx, zone in enumerate(zones_list):
            if z_idx < h_fill:
                for i in zone: 
                    set_color(px, i, scale(C_GOLD, 0.3))
            if abs(z_idx - h_fill) < 0.5:
                for i in zone: 
                    set_color(px, i, C_WHITE)
    send_frame(px)

# ========= MAIN LOOP =========
def run_show():
    rf = None
    if HAS_RF: rf = RFManager()
    
    print(f">>> Iniciando Video: {VIDEO_FILE}")
    start_mpv(VIDEO_FILE)
    if not connect_ipc():
        print("[ERROR] MPV no responde.")
        return

    print(">>> Sincronizando (Motor Stateless)...")
    video_started = False
    last_ranger_processed = -1 
    
    try:
        while True:
            if mpv_proc.poll() is not None: break
            t_video = get_video_time()
            
            if t_video < 0:
                time.sleep(0.04)
                continue

            if not video_started:
                if t_video > 0.1:
                    video_started = True
                    print("\n>>> VIDEO DETECTADO!")
                else:
                    send_frame(frame_fill(C_OFF))
                    time.sleep(0.04)
                    continue
            
            # --- SELECTOR DE ESCENA ---
            if t_video < T_RITA_END:
                render_rita(t_video)
            elif t_video < T_ZEDD_END:
                render_zedd(t_video - T_RITA_END)
            elif t_video < T_START_ALFA:
                render_alarm(t_video - T_START_ALARM)
            elif t_video < T_START_TELEPORT:
                render_alfa(t_video - T_START_ALFA)
            elif t_video < T_START_PREMORPH:
                render_teleport(t_video - T_START_TELEPORT)
            elif t_video < T_START_RED:
                render_zordon(t_video - T_START_PREMORPH)
            
            elif t_video < T_START_MEGAZORD:
                if t_video < T_START_NEED_MZ:
                    curr_ranger_idx = -1
                    for idx, (start_t, _, _, _, _) in enumerate(RANGERS_TIMELINE):
                        if t_video >= start_t: curr_ranger_idx = idx
                        else: break
                    
                    if curr_ranger_idx >= 0:
                        if curr_ranger_idx > last_ranger_processed:
                            if last_ranger_processed >= 0:
                                prev_z_leds = RANGERS_TIMELINE[last_ranger_processed][4]
                                prev_z_col  = RANGERS_TIMELINE[last_ranger_processed][3]
                                for i in prev_z_leds: ACTIVE_ZORDS[i] = prev_z_col
                            last_ranger_processed = curr_ranger_idx
                            print(f"\nRanger: {RANGERS_TIMELINE[curr_ranger_idx][1]}")
                        
                        r_start, _, r_leds, r_col, z_leds = RANGERS_TIMELINE[curr_ranger_idx]
                        if curr_ranger_idx < len(RANGERS_TIMELINE) - 1:
                            r_end = RANGERS_TIMELINE[curr_ranger_idx+1][0]
                        else:
                            r_end = T_START_NEED_MZ
                        
                        render_ranger_morph(t_video - r_start, r_end - r_start, r_leds, r_col, z_leds)
                else:
                    if last_ranger_processed == 5:
                         prev_z_leds = RANGERS_TIMELINE[5][4]
                         prev_z_col  = RANGERS_TIMELINE[5][3]
                         for i in prev_z_leds: ACTIVE_ZORDS[i] = prev_z_col
                         last_ranger_processed = 6
                    
                    render_call_megazord(t_video - T_START_NEED_MZ)

            elif t_video < T_START_FINAL:
                render_megazord_complex(t_video - T_START_MEGAZORD)

            else:
                px = [C_OFF] * N
                FINAL_ZONES = set(ZONE1 + ZONE2)
                for i in FINAL_ZONES: px[i] = C_FINAL_AMBIENT
                for idx, col in ACTIVE_ZORDS.items(): px[idx] = col
                for _, _, r_leds, r_col, _ in RANGERS_TIMELINE:
                    for i in r_leds: px[i] = r_col
                
                for i in LEDS_VILLAINS_FULL: px[i] = C_RITA
                for i in LEDS_ZEDD: px[i] = C_ZEDD

                send_frame(px)
                time.sleep(0.5)

            time.sleep(0.04)

    except KeyboardInterrupt:
        print("\nCancelado.")
    finally:
        if rf: rf.cleanup()
        cleanup_mpv()

if __name__ == "__main__":
    run_show()