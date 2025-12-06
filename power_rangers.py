#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# power_rangers_show.py
# VERSIÓN FINAL PULIDA (v3):
# - Villanos usan la columna derecha del estante 1 (Z1_R).
# - Final: Rangers y Zords se quedan en SU color, con fondo blanco más intenso.

import time
import math
import random
import sys
import requests
from itertools import chain

# --- IMPORTACIÓN SEGURA ---
try:
    from layout import * # Importamos N e INDEX
    # Fallbacks de seguridad por si layout.py es antiguo
    if "Z1_T" not in INDEX: INDEX["Z1_T"] = list(range(105, 123))
    if "T_T" not in INDEX:  INDEX["T_T"]  = list(range(69, 87))
    if "Z1_R" not in INDEX: INDEX["Z1_R"] = [] # Columna derecha estante 1
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

# COLORES
C_OFF    = (0, 0, 0)
# Luz ambiente final MÁS INTENSA para ver bien la estantería
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

# ========= MAPEO DE ZONAS =========

# 1. ZONA 1 (ARRIBA)
Z1_STRIP = INDEX["Z1_T"]
Z1_SIDE_R = INDEX["Z1_R"] # Columna derecha para los malos

LEDS_VILLAINS    = Z1_STRIP[0:5]
# Unimos las figuras con la columna lateral para el efecto de villanos
LEDS_VILLAINS_FULL = LEDS_VILLAINS + Z1_SIDE_R

LEDS_ZORD_YELLOW = Z1_STRIP[5:7]
LEDS_ZORD_BLACK  = [Z1_STRIP[7]]
LEDS_ZORD_RED    = [Z1_STRIP[8]]
LEDS_ZORD_PINK   = Z1_STRIP[9:11]
LEDS_ZORD_BLUE   = Z1_STRIP[11:13]
LEDS_ZORD_WHITE  = Z1_STRIP[13:18]

# 2. ZONA 2 (MEDIO) - Rangers, Zordon y Alfa
# Invertimos para contar desde la DERECHA
Z2_STRIP = list(reversed(INDEX["T_T"]))

POS_R_RED    = Z2_STRIP[4:6]
POS_R_YELLOW = Z2_STRIP[6:8]
POS_R_BLACK  = Z2_STRIP[8:10]
POS_R_BLUE   = Z2_STRIP[9:11]
POS_R_PINK   = Z2_STRIP[11:13]
POS_R_WHITE  = Z2_STRIP[13:15]

LEDS_ZORDON  = Z2_STRIP[7:11] 
LEDS_ALFA    = LEDS_ZORDON 

# 3. LATERALES (Generales, para efectos de beam)
ALL_SIDES = []
for k, v in INDEX.items():
    if "_L" in k or "_R" in k: 
        ALL_SIDES.extend(v)

# SECUENCIA RANGERS
RANGERS_SEQ = [
    ("RED",    POS_R_RED,    C_RED,    LEDS_ZORD_RED,    "vortex"),
    ("BLACK",  POS_R_BLACK,  C_BLACK,  LEDS_ZORD_BLACK,  "rain"),
    ("BLUE",   POS_R_BLUE,   C_BLUE,   LEDS_ZORD_BLUE,   "beam"),
    ("YELLOW", POS_R_YELLOW, C_YELLOW, LEDS_ZORD_YELLOW, "climb"),
    ("PINK",   POS_R_PINK,   C_PINK,   LEDS_ZORD_PINK,   "comet"),
    ("WHITE",  POS_R_WHITE,  C_WHITE,  LEDS_ZORD_WHITE,  "lightning"),
]

# ========= UTILIDADES GRÁFICAS =========

# Diccionario para guardar qué Zords están encendidos y de qué color
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

def frame_fill(color):
    return [color] * N

def get_base_frame():
    """Frame base NEGRO + Zords activos"""
    px = [C_OFF] * N
    for idx, col in ACTIVE_ZORDS.items():
        px[idx] = col
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

# ========= EFECTOS (Sobre fondo negro) =========

def effect_vortex(base_col, duration):
    frames = int(20 * duration)
    zones = [INDEX["B_T"], INDEX["M_T"], INDEX["T_T"], INDEX["Z1_T"]]
    for f in range(frames):
        t = f/frames
        px = get_base_frame()
        for z_idx, zone in enumerate(zones):
            offset = int((t * 20) + (z_idx * 3)) % len(zone)
            for i in range(len(zone)):
                dist = (i - offset) % len(zone)
                if dist < 6:
                    k = 1.0 - (dist/6.0)
                    add_color(px, zone[i], scale(base_col, k))
        send_frame(px); time.sleep(0.05)

def effect_rain(base_col, duration):
    frames = int(20 * duration)
    for f in range(frames):
        px = get_base_frame()
        for i in range(N):
            if i not in ACTIVE_ZORDS: 
                if random.random() < 0.03: add_color(px, i, base_col)
                elif random.random() < 0.06: add_color(px, i, scale(base_col, 0.4))
        send_frame(px); time.sleep(0.05)

def effect_beam(base_col, duration):
    frames = int(20 * duration)
    # Usamos TODOS los laterales para el efecto beam
    V_CHAINS = ALL_SIDES
    T_CHAINS = INDEX["B_T"] + INDEX["M_T"] + INDEX["T_T"] + INDEX["Z1_T"]
    for f in range(frames):
        t = f/frames
        px = get_base_frame()
        k = (math.sin(t * 10) + 1) / 2 
        side_c = scale(base_col, 0.4 + 0.6*k)
        for i in V_CHAINS: set_color(px, i, side_c)
        scan = int(t * 40) % 20
        for i in T_CHAINS:
            if (i % 20) == scan: add_color(px, i, C_WHITE)
        send_frame(px); time.sleep(0.05)

def effect_climb(base_col, duration):
    frames = int(20 * duration)
    for f in range(frames):
        t = (f/frames) * 4
        phase = t % 1.0
        px = get_base_frame()
        h_active = phase * 4
        zones = [INDEX["B_L"]+INDEX["B_R"]+INDEX["B_T"], 
                 INDEX["M_L"]+INDEX["M_R"]+INDEX["M_T"],
                 INDEX["T_L"]+INDEX["T_R"]+INDEX["T_T"],
                 INDEX["Z1_L"]+INDEX["Z1_R"]+INDEX["Z1_T"]]
        for z_idx, zone in enumerate(zones):
            dist = abs(z_idx - h_active)
            if dist < 1.0:
                k = 1.0 - dist
                for i in zone: 
                    if i not in ACTIVE_ZORDS: add_color(px, i, scale(base_col, k))
        send_frame(px); time.sleep(0.05)

def effect_comet(base_col, duration):
    frames = int(24 * duration)
    path = INDEX["B_L"] + INDEX["M_L"] + INDEX["T_L"] + INDEX["Z1_L"] + \
           INDEX["Z1_T"] + \
           list(reversed(INDEX["Z1_R"] + INDEX["T_R"] + INDEX["M_R"] + INDEX["B_R"])) + \
           list(reversed(INDEX["B_T"]))
    L = len(path)
    for f in range(frames):
        head = int((f * 2) % L)
        px = get_base_frame()
        for k in range(20):
            idx = (head - k) % L
            intensity = 1.0 - (k/20.0)
            add_color(px, path[idx], scale(base_col, intensity))
        send_frame(px); time.sleep(0.04)

def effect_lightning(base_col, duration):
    frames = int(24 * duration)
    for f in range(frames):
        px = get_base_frame()
        for _ in range(4):
            pos = random.randint(0, N-1)
            if pos not in ACTIVE_ZORDS:
                set_color(px, pos, C_WHITE)
                if pos+1 < N: add_color(px, pos+1, scale(base_col, 0.6))
        send_frame(px); time.sleep(0.04)

EFFECTS_MAP = {
    "vortex": effect_vortex, "rain": effect_rain, "beam": effect_beam,
    "climb": effect_climb, "comet": effect_comet, "lightning": effect_lightning
}

# ========= ESCENAS =========

def scene_villains(duration=6.0):
    print(">>> Villanos (con columna lateral)")
    t0 = time.time()
    while (time.time() - t0) < duration:
        t = time.time() - t0
        k = 0.2 + 0.8 * ((math.sin(t*3)+1)/2)
        col = mix(C_RITA, C_ZEDD, 0.5+0.5*math.sin(t))
        px = get_base_frame()
        # Usamos la lista extendida (figuras + columna derecha)
        for i in LEDS_VILLAINS_FULL: set_color(px, i, scale(col, k))
        send_frame(px); time.sleep(0.05)

def scene_alfa_panic(duration=3.0):
    print(">>> Alfa 5 Panic")
    t0 = time.time()
    while (time.time() - t0) < duration:
        px = get_base_frame()
        state = int(time.time() * 18) % 2
        alfa_color = C_ALFA if state == 0 else C_WHITE
        for i in LEDS_ALFA: set_color(px, i, alfa_color)
        send_frame(px); time.sleep(0.05)

def scene_zordon_wake(duration=4.0):
    print(">>> Zordon Wake")
    t0 = time.time()
    while (time.time() - t0) < duration:
        px = get_base_frame()
        z_int = random.uniform(0.6, 1.0)
        for i in LEDS_ZORDON: set_color(px, i, scale(C_ZORDON, z_int))
        send_frame(px); time.sleep(0.04)

def play_ranger_sequence(name, ranger_leds, color, zord_leds, effect_name):
    print(f">>> RANGER: {name}")
    
    # 1. Llamada
    for k in range(30):
        px = get_base_frame()
        brite = (math.sin(k*0.5)+1)/2
        for i in ranger_leds: set_color(px, i, scale(color, brite))
        # Zordon vigila (opcional, descomentar si se quiere)
        # for i in LEDS_ZORDON: set_color(px, i, scale(C_ZORDON, 0.3)) 
        send_frame(px); time.sleep(0.05)

    # 2. Poder
    print(f"   -> Efecto {effect_name}")
    effect_func = EFFECTS_MAP.get(effect_name, effect_beam)
    effect_func(color, duration=4.0)

    # 3. Morphin
    print("   -> Morphin...")
    steps = 40
    for k in range(steps):
        t = k/steps
        px = get_base_frame()
        # Parpadeo del color del Ranger
        if k % 3 == 0:
            for i in ranger_leds: set_color(px, i, color)
        
        h_zone = int(t * 4) 
        if h_zone < 4:
            zone_idx = [INDEX["B_T"], INDEX["M_T"], INDEX["T_T"], INDEX["Z1_T"]][h_zone]
            for _ in range(3):
                s = random.choice(zone_idx)
                if s not in ACTIVE_ZORDS: set_color(px, s, C_WHITE)

        if t > 0.5:
            z_brite = (t-0.5)/0.5
            for i in zord_leds: set_color(px, i, scale(color, z_brite))
            
        send_frame(px); time.sleep(0.05)

    # 4. Activar Zord (Persistente)
    for i in zord_leds: ACTIVE_ZORDS[i] = color
    
    # Pausa para fijar
    for _ in range(15):
        px = get_base_frame()
        for i in zord_leds: add_color(px, i, scale(C_WHITE, 0.5))
        send_frame(px); time.sleep(0.05)

def scene_megazord(duration=6.0):
    print(">>> MEGAZORD")
    t0 = time.time()
    while (time.time() - t0) < duration:
        px = get_base_frame()
        pulse = (math.sin(time.time()*15)+1)/2
        for idx, base_col in ACTIVE_ZORDS.items():
            gold = mix(base_col, C_GOLD, pulse)
            set_color(px, idx, gold)
        side_pwr = scale(C_GOLD, 0.3 + 0.4*pulse)
        for i in ALL_SIDES: set_color(px, i, side_pwr)
        send_frame(px); time.sleep(0.03)

# ========= MAIN =========
if __name__ == "__main__":
    rf = None
    if HAS_RF: rf = RFManager()
    
    try:
        # Reset inicial a negro
        send_frame(frame_fill(C_OFF)); time.sleep(0.5)
        
        # SHOW
        scene_villains()
        scene_alfa_panic()
        scene_zordon_wake()
        
        for r_data in RANGERS_SEQ:
            play_ranger_sequence(*r_data)
            
        scene_megazord()
        
        # === FINAL: ILUMINACIÓN PERSONALIZADA ===
        print(">>> Iluminación Final (Rangers + Zords + Fondo Brillante)")
        
        # Definimos las zonas de fondo (Estantes 1 y 2 completos)
        AMBIENT_ZONES = set(ZONE1 + ZONE2)
        
        # Preparamos el mapa final de Rangers {led: color}
        FINAL_RANGER_POSITIONS = {}
        for _, r_leds, r_col, _, _ in RANGERS_SEQ:
            for led in r_leds:
                FINAL_RANGER_POSITIONS[led] = r_col
        
        # Fade In hasta el estado final
        for k in range(50):
            factor = k/50.0
            px = [C_OFF] * N
            
            # 1. Fondo Blanco Intenso
            bg_col = scale(C_FINAL_AMBIENT, factor)
            for i in AMBIENT_ZONES:
                px[i] = bg_col
            
            # 2. Zords en su color (se superponen al fondo)
            for idx, col in ACTIVE_ZORDS.items():
                px[idx] = col
                
            # 3. Rangers en su color (se superponen al fondo)
            for idx, col in FINAL_RANGER_POSITIONS.items():
                px[idx] = col
            
            send_frame(px); time.sleep(0.05)
            
        # Mantener el estado final indefinidamente
        final_px = [C_OFF] * N
        for i in AMBIENT_ZONES: final_px[i] = C_FINAL_AMBIENT
        for idx, col in ACTIVE_ZORDS.items(): final_px[idx] = col
        for idx, col in FINAL_RANGER_POSITIONS.items(): final_px[idx] = col
        send_frame(final_px)
        print(">>> Fin del show. Luces fijas.")
        
    except KeyboardInterrupt:
        print("\nCancelado.")
    finally:
        if rf: rf.cleanup()