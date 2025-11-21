#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# regreso_al_futuro_torre_reloj_v2.py
# - Actualizado a 132 LEDs con nuevo estante superior (Zona 1)
# - Zonas renombradas 1..4 (1=super top; 4=abajo)
# - Nubes SOLO en Zona 1 (nuevo estante)
# - El rayo nace en 101–102 (1-based), recorre hasta 132, salta a 69→61, salta a 55–54 (pausa reloj) y continúa 55→42 (impacto coche)
# - Mantiene reproducción de vídeo con mpv e Hyperion (igual al original)

import os, time, math, random, json, socket, subprocess, atexit, argparse, requests
from typing import List

from rpi_rf import RFDevice



RF_CODES = {
    "front":        1744397,
    "interior":     1744398,
    "rear":         1744399,
    "blue_front":   1744400,
    "blue_rear":    1744401,
    "wheels":       1744402,
    "flux":         1744403,
}

# ========= CONFIG =========
VIDEO_FILE_DEFAULT = "/home/pi/bttflargo.mp4"
HOST       = "http://localhost:8090"
TOKEN      = None
PRIORITY   = 64
ORIGIN     = "bttf"
FPS        = 30
GAMMA      = 1.0
AUDIO_DEVICE = "alsa/hdmi:CARD=vc4hdmi,DEV=0"

# ========= TIMELINE BASE =========
# Mantén tus marcas (ajustables con --clock-offset / --car-offset)
T_CLOCK_BASE  = 139.2   # golpe del rayo en el reloj (55–54)
T_IMPACT_BASE = 143.5   # impacto en el DeLorean (42)
T_BLUE_SPARK_START  = 149.2   # serpientes azules previas/convergentes (decorativo post)
T_ORANGE_SPARK_BASE = 155.59  # chisporroteo naranja decorativo post

# ========= LAYOUT (132 LEDs; 0-based) =========
# Mismo layout original (0..95) + nuevo estante (96..131)
# Antiguas bandas (para compatibilidad con efectos):
#   Abajo (B_*): 0..29
#   Medio (M_*): 30..59
#   Arriba (T_*): 60..95
# Nuevo estante (Zona 1): 96..131
SEGMENTS_96 = [
    ("B_L", 6), ("B_T", 18), ("B_R", 6),
    ("M_R", 6), ("M_T", 18), ("M_L", 6),
    ("T_L", 9), ("T_T", 18), ("T_R", 9),
]
SEGMENT_REVERSED_96 = {
    "B_L": False, "B_T": False, "B_R": True,
    "M_R": False, "M_T": True,  "M_L": True,
    "T_L": False, "T_T": False, "T_R": True,
}

INDEX = {}
start = 0
for name, length in SEGMENTS_96:
    ids = list(range(start, start + length))
    if SEGMENT_REVERSED_96.get(name, False):
        ids.reverse()
    INDEX[name] = ids
    start += length

# Añadimos el nuevo estante superior (36 LEDs) como tres secciones de 9/18/9
# El usuario definió (1-based):
#   97-105 = arriba del todo a la derecha (de abajo a arriba)
#   106-123 = centro (de derecha a izquierda)
#   124-132 = izquierda (de arriba a abajo)
# Pasamos a 0-based:
Z1_R = list(range(96, 105))      # (97..105 1-based) sentido "abajo→arriba"
Z1_T = list(range(105, 123))     # (106..123 1-based) sentido "derecha→izquierda"
Z1_L = list(range(123, 132))     # (124..132 1-based) sentido "arriba→abajo"

# ========= TAMAÑO TOTAL =========
N = 132

# ========= ZONAS NUMÉRICAS =========
ZONE1 = Z1_R + Z1_T + Z1_L               # nuevo estante (96..131)
ZONE2 = INDEX["T_L"] + INDEX["T_T"] + INDEX["T_R"]  # antiguo top (60..95)
ZONE3 = INDEX["M_L"] + INDEX["M_T"] + INDEX["M_R"]  # medio (30..59)
ZONE4 = INDEX["B_L"] + INDEX["B_T"] + INDEX["B_R"]  # abajo (0..29)

ZONE1_SET = set(ZONE1)
ZONE2_SET = set(ZONE2)
ZONE3_SET = set(ZONE3)
ZONE4_SET = set(ZONE4)

# ========= PUNTOS CLAVE (0-based) =========
LED_CLOCK = [54, 55]   # reloj (user 55–54 1-based)
LED_CAR   = [42, 41]   # coche

# ========= PATH DEL RAYO =========
# 1) Nace en 101–102 (1-based) => 100–101 (0-based) y se mueve hacia 132 (131 0-based)
PRE_PATH_1 = list(range(100, 132))            # 100→131 a través de Zona 1
# 2) Salta a 69 y baja hasta 61 (1-based) => 68..60 (0-based)
PRE_PATH_2 = list(range(68, 59, -1))          # 68→60 (antiguo top)
# 3) Salta al reloj 55–54 (0-based) y pausa breve (T_CLOCK)
PAUSE_CLOCK_LEDS = LED_CLOCK                  # pausa aquí
# 4) Continúa 55→42 (0-based) hasta el coche (impacto)
TRAVEL_PATH_TO_CAR = list(range(55, 40, -1))  # 55→41 (incluye 42)

# Duraciones del prefase (antes de T_CLOCK) y de viaje al coche (T_CLOCK→T_IMPACT)
PRE_TOTAL_S = 2.4       # tiempo total para recorrer PRE_PATH_1 + PRE_PATH_2
PRE_HOLD_CLOCK = 0.18   # pausa en el reloj (blanco) antes de empezar el viaje al coche

# ========= HYPERION =========
headers = {"Content-Type": "application/json"}
if TOKEN: headers["Authorization"] = f"Bearer {TOKEN}"

def clamp(x): return max(0, min(255, int(x)))
def lerp(a, b, t): return a + (b - a) * t
def mix(c1, c2, t): return (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))
def scale(c, k): return (c[0] * k, c[1] * k, c[2] * k)

WHITE          = (255, 255, 255)
ELECTRIC_BLUE  = (150, 200, 255)
DEEP_BLUE      = (30, 90, 200)
ORANGE_INTENSE = (255, 80, 0)

# ======== CORTAFUEGOS BLANCO ========
# Blanco SOLO permitido por defecto en Zona 1 (nuevo estante).
def white_allowed(i: int) -> bool:
    return i in ZONE1_SET

def apply_gamma(c):
    if GAMMA == 1.0: return c
    r, g, b = c
    gfun = lambda v: 255 * ((v / 255.0) ** GAMMA)
    return (gfun(r), gfun(g), gfun(b))

def pack(pixels):
    flat = []
    for r, g, b in pixels:
        r, g, b = apply_gamma((r, g, b))
        flat += [clamp(r), clamp(g), clamp(b)]
    return flat

def send_frame(pixels, duration=-1):
    payload = {"command": "color", "color": pack(pixels),
               "priority": PRIORITY, "origin": ORIGIN, "duration": duration}
    try:
        requests.post(f"{HOST}/json-rpc", headers=headers, json=payload, timeout=2)
    except Exception:
        pass

def frame_fill(c): return [c] * N
def add(px, i, c):
    if 0 <= i < N:
        r, g, b = px[i]; cr, cg, cb = c
        px[i] = (r + cr, g + cg, b + cb)

# ========= EFECTOS BASE =========
def idle_ambient(phase: float):
    k = 0.08 + 0.06 * math.sin(phase * 2 * math.pi)
    base = scale(ELECTRIC_BLUE, k)
    return frame_fill(base)

def _add_white_guarded(px, i, val):
    if white_allowed(i): add(px, i, scale(WHITE, val))
    else:                add(px, i, scale(ELECTRIC_BLUE, val * 0.8))  # fallback azul

def white_flash_local(px, indices, power=2.2, force=False):
    for i in indices:
        if force or white_allowed(i):
            add(px, i, scale(WHITE, 2.2 * power))
            if i - 1 >= 0: add(px, i - 1, scale(WHITE, 0.7 * power))
            if i + 1 < N: add(px, i + 1, scale(WHITE, 0.7 * power))
        else:
            # fallback azul si no está permitido
            add(px, i, scale(ELECTRIC_BLUE, 2.2 * power))
            if i - 1 >= 0: add(px, i - 1, scale(ELECTRIC_BLUE, 0.7 * power))
            if i + 1 < N: add(px, i + 1, scale(ELECTRIC_BLUE, 0.7 * power))

def blue_flash_local(px, indices, power=2.2):
    for i in indices:
        add(px, i, scale(ELECTRIC_BLUE, 2.2 * power))
        if i - 1 >= 0: add(px, i - 1, scale(ELECTRIC_BLUE, 0.8 * power))
        if i + 1 < N: add(px, i + 1, scale(ELECTRIC_BLUE, 0.8 * power))

def crackle(px, centers, spread=5, density=0.6, color='white'):
    if color == 'white':
        base = WHITE; mix_with = ELECTRIC_BLUE; mix_amt = 0.4
    elif color == 'blue':
        base = ELECTRIC_BLUE; mix_with = WHITE; mix_amt = 0.2
    elif color == 'orange':
        base = ORANGE_INTENSE; mix_with = WHITE; mix_amt = 0.35
    else:
        base = ELECTRIC_BLUE; mix_with = WHITE; mix_amt = 0.2
    for c in centers:
        for j in range(-spread, spread + 1):
            i = c + j
            if 0 <= i < N and random.random() < density * (1 - abs(j) / (spread + 1)):
                col = mix(base, mix_with, mix_amt)
                if color == 'white' and not white_allowed(i):
                    col = ELECTRIC_BLUE
                add(px, i, col)

def draw_along_path(px, path: List[int], head_pos: float, tail: int = 10, color='blue', head_gain=2.0):
    """Dibuja un trazo con 'head' que avanza a lo largo de 'path' [índices absolutos]."""
    if not path: return
    head_idx = int(max(0, min(len(path) - 1, round(head_pos * (len(path) - 1)))))
    for j in range(tail):
        idx = head_idx - j
        if idx < 0: break
        led = path[idx]
        fade = max(0.0, 1.0 - j / max(1, tail))
        if color == 'white':
            add(px, led, scale(WHITE, head_gain * fade))
            if led - 1 >= 0: add(px, led - 1, scale(WHITE, 0.45 * fade))
            if led + 1 < N: add(px, led + 1, scale(WHITE, 0.45 * fade))
        else:
            add(px, led, scale(ELECTRIC_BLUE, head_gain * fade))
            if led - 1 >= 0: add(px, led - 1, scale(ELECTRIC_BLUE, 0.45 * fade))
            if led + 1 < N: add(px, led + 1, scale(ELECTRIC_BLUE, 0.45 * fade))

def serpents_converge(px, progress, color, tail=5, head_gain=2.4, center_gain=1.8):
    SPARK_LEFT_LED, SPARK_RIGHT_LED = 36, 54
    SPARK_CENTER_LED = (SPARK_LEFT_LED + SPARK_RIGHT_LED) // 2
    progress = max(0.0, min(1.0, progress))
    center = SPARK_CENTER_LED
    left_head  = int(round(lerp(SPARK_LEFT_LED, center, progress)))
    right_head = int(round(lerp(SPARK_RIGHT_LED, center + 1, progress)))
    for k in range(tail):
        fade = max(0.0, 1.0 - k / max(1, tail))
        idx_left = left_head - k
        if SPARK_LEFT_LED <= idx_left <= center:
            add(px, idx_left, scale(color, head_gain * fade))
        idx_right = right_head + k
        if center < idx_right <= SPARK_RIGHT_LED:
            add(px, idx_right, scale(color, head_gain * fade))
    for idx in (center, center + 1):
        if SPARK_LEFT_LED <= idx <= SPARK_RIGHT_LED:
            add(px, idx, scale(color, center_gain))

def apply_converge_effect(px, progress, color, crackle_color, tail=5, bloom_base=0.35, bloom_amp=0.25, head_gain=2.4, center_gain=1.8):
    SPARK_LEFT_LED, SPARK_RIGHT_LED = 36, 54
    SPARK_CENTER_LED = (SPARK_LEFT_LED + SPARK_RIGHT_LED) // 2
    serpents_converge(px, progress, color, tail=tail, head_gain=head_gain, center_gain=center_gain)
    base_bloom = bloom_base + bloom_amp * math.sin(progress * math.pi)
    for idx in range(SPARK_LEFT_LED, SPARK_RIGHT_LED + 1):
        dist = abs(idx - SPARK_CENTER_LED)
        weight = max(0.1, 1.0 - dist / max(1, (SPARK_RIGHT_LED - SPARK_LEFT_LED + 1)))
        add(px, idx, scale(color, base_bloom * weight))
    centers = [SPARK_LEFT_LED, SPARK_RIGHT_LED, SPARK_CENTER_LED]
    crackle(px, centers, spread=2, density=0.65, color=crackle_color)

def apply_orange_converge_effect(px, progress):
    apply_converge_effect(px, progress, ORANGE_INTENSE, 'orange')

def apply_blue_converge_effect(px, progress):
    apply_converge_effect(px, progress, ELECTRIC_BLUE, 'blue', bloom_base=0.25, bloom_amp=0.2)

# ========= FX por zona =========
def storm_clouds_zone1(px, density: float = 0.14):
    """Nubes blancas SOLO en la Zona 1 (nuevo estante)."""
    if not ZONE1: return
    if random.random() < density:
        size = random.randint(2, 5)
        center = random.choice(ZONE1)
        for j in range(-size, size + 1):
            idx = center + j
            if idx in ZONE1_SET:
                _add_white_guarded(px, idx, 1.4 * (1 - abs(j) / (size + 1)))

def global_flash_white(hold_ms=550, power=1.0):
    """Flash blanco global (impacto), sin guardas."""
    px = frame_fill(scale(WHITE, 2.5 * power))
    send_frame(px, duration=int(hold_ms))

# ========= MPV IPC =========
SOCK_PATH = "/tmp/mpv-bttf.sock"
MPV_LOG   = "/tmp/mpv-bttf.log"
mpv_proc  = None
ipc_sock  = None

def cleanup():
    try:
        if ipc_sock: ipc_sock.close()
    except: pass
    try:
        if mpv_proc and mpv_proc.poll() is None:
            mpv_proc.terminate()
    except: pass
    try:
        send_frame(frame_fill((0, 0, 0)), duration=500)
    except: pass

atexit.register(cleanup)

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
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(SOCK_PATH): break
        time.sleep(0.05)
    global ipc_sock
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(SOCK_PATH)
            ipc_sock = s
            return
        except Exception:
            time.sleep(0.05)
    raise RuntimeError("No se pudo conectar al socket IPC de mpv")

def mpv_get_prop(prop: str, timeout=0.2):
    req = {"command": ["get_property", prop], "request_id": 1}
    if not ipc_sock: return None
    try:
        ipc_sock.sendall((json.dumps(req) + "\n").encode("utf-8"))
        ipc_sock.settimeout(timeout)
        data = b""
        while True:
            chunk = ipc_sock.recv(4096)
            if not chunk: break
            data += chunk
            if b"\n" in data:
                lines = data.split(b"\n")
                for line in lines:
                    if not line.strip(): continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                        if msg.get("request_id") == 1 and msg.get("error") == "success":
                            return msg.get("data")
                    except:
                        continue
                break
    except Exception:
        return None
    return None

# ========= LOOP =========
def run_show_with_video(video_path, clock_offset, car_offset):
    random.seed()
    start_mpv(video_path)
    connect_ipc()

    # Tiempos efectivos (permite offsets CLI)
    T_CLOCK  = T_CLOCK_BASE  + clock_offset
    T_IMPACT = T_IMPACT_BASE + car_offset
    T_BLUE_SPARK   = T_BLUE_SPARK_START
    T_ORANGE_SPARK = T_ORANGE_SPARK_BASE
    T_FALLO_MOTOR = 40.23
    T_PRUEBA_MOTOR =  49.27
    T_PRUEBA_MOTOR_LEN = 4
    T_ENCENDIDO= 66.7
    T_RUEDAS= 127.53


    # Flags de disparo
    fired_clock = False
    fired_travel = False
    fired_impact = False
    fired_blue = False
    fired_orange = False

    # Estados
    pre_start_time = None
    travel_start_time = None
    white_hold_until  = None
    post_set_time     = None
    post_hold_s       = 4.0
    POST_FADE_S       = 1.8
    lucesfront = 0
    lucesback = 0
    ruedas = 0
    azules = 0

    rfdevice = RFDevice(17)
    rfdevice.enable_tx()
    rfdevice.tx_repeat = 4
    rfprotocol = 1
    rfpulselength = 396
    rflength = 24
    try:
        while True:
            if mpv_proc.poll() is not None:
                break

            t = mpv_get_prop("time-pos")
            if t is None:
                time.sleep(1.0 / FPS)
                continue

            # Forzamos el flash global durante su hold
            if white_hold_until is not None and t < white_hold_until:
                send_frame(frame_fill(scale(WHITE, 2.5)))
                time.sleep(1.0 / FPS)
                continue

            # base ambiente
            px = idle_ambient(phase=(t or 0) * 0.25)

            # Nubes SOLO en Zona 1 antes del rayo
            if t < (T_CLOCK - 0.05):
                storm_clouds_zone1(px, density=0.14)
            if t >= 2 and t < 2.1:
                if lucesfront == 0:
                    print("lucesfront")
                    rfdevice.tx_code(RF_CODES["front"], rfprotocol, rfpulselength, rflength)
                    lucesfront = 1
            if t >= 2.2 and t < 2.3:
                if lucesback == 0:
                    print("lucesback")
                    rfdevice.tx_code(RF_CODES["rear"], rfprotocol, rfpulselength, rflength)
                    lucesback =1
            if t >= T_FALLO_MOTOR and t < T_FALLO_MOTOR + 0.1:
                if lucesfront == 1:
                    rfdevice.tx_code(RF_CODES["front"], rfprotocol, rfpulselength, rflength)
                    lucesfront =0
            if t >= T_FALLO_MOTOR+0.2 and t < T_FALLO_MOTOR + 0.3:
                if lucesback == 1:
                    rfdevice.tx_code(RF_CODES["rear"], rfprotocol, rfpulselength, rflength)
                    lucesback =0
            
            if t >= T_ENCENDIDO and t < T_ENCENDIDO + 0.1:
                if lucesfront == 0:
                    rfdevice.tx_code(RF_CODES["front"], rfprotocol, rfpulselength, rflength)
                    lucesfront =1
            if t >= T_ENCENDIDO+0.2 and t < T_ENCENDIDO + 0.3:
                if lucesback == 0:
                    rfdevice.tx_code(RF_CODES["rear"], rfprotocol, rfpulselength, rflength)
                    lucesback =1
            if t >= T_RUEDAS and t < T_RUEDAS + 0.2:
                if ruedas == 0:
                    rfdevice.tx_code(RF_CODES["wheels"], rfprotocol, rfpulselength, rflength)
                    ruedas =1
            if t >= T_RUEDAS + 1.5 and t < T_RUEDAS + 1.7:
                if ruedas == 0:
                    rfdevice.tx_code(RF_CODES["wheels"], rfprotocol, rfpulselength, rflength)
                    ruedas =1

            # Prefase: desde T_CLOCK - PRE_TOTAL_S hasta T_CLOCK (recorre PRE_PATH_1 y PRE_PATH_2)
            if t >= (T_CLOCK - PRE_TOTAL_S) and t < T_CLOCK:
                if pre_start_time is None:
                    pre_start_time = t
                    # chispa inicial en 101–102 (0-based 100–101)
                    white_flash_local(px, [100, 101], power=2.0)  # permitido en Zona 1
                # Progreso 0..1 de todo el prefase
                p = max(0.0, min(1.0, (t - pre_start_time) / PRE_TOTAL_S))
                # Recorremos primero el path de Zona 1 y luego el viejo top
                len1 = len(PRE_PATH_1)
                len2 = len(PRE_PATH_2)
                total = len1 + len2
                pos = p * (total - 1)
                if pos < len1:
                    head_pos = pos / max(1, len1 - 1)
                    draw_along_path(px, PRE_PATH_1, head_pos, tail=8, color='white', head_gain=2.3)
                else:
                    pos2 = pos - len1
                    head_pos2 = pos2 / max(1, len2 - 1)
                    # En el viejo top lo pintamos AZUL para no colar blanco fuera de Zona 1
                    draw_along_path(px, PRE_PATH_2, head_pos2, tail=8, color='blue', head_gain=2.0)

            # Golpe al reloj (pausa breve)
            if t >= T_CLOCK and not fired_clock:
                # blanco FORZADO en el reloj (override guard)
                white_flash_local(px, LED_CLOCK, power=2.3, force=True)
                crackle(px, LED_CLOCK, spread=5, density=0.9, color='white')
                fired_clock = True
                travel_start_time = t + PRE_HOLD_CLOCK  # pequeña pausa en el reloj

            # Viaje 55→42 (T_CLOCK→T_IMPACT)
            if fired_clock and not fired_travel:
                dur = max(0.01, T_IMPACT - travel_start_time)
                u = 0.0 if dur == 0 else min(1.0, max(0.0, (t - travel_start_time) / dur))
                # Viaje AZUL hasta el coche (el destello blanco grande llegará en el impacto)
                draw_along_path(px, TRAVEL_PATH_TO_CAR, u, tail=10, color='blue', head_gain=2.1)
                if u >= 1.0:
                    fired_travel = True

            if t >= T_IMPACT and t< T_IMPACT+0.1:
                if azules == 0:
                    rfdevice.tx_code(RF_CODES["blue_front"], rfprotocol, rfpulselength, rflength)
                    azules = 1
            
            if t >= T_IMPACT+0.2 and t< T_IMPACT+0.3:
                if azules == 1:
                    rfdevice.tx_code(RF_CODES["blue_rear"], rfprotocol, rfpulselength, rflength)
                    azules = 0
            # Impacto en el DeLorean
            if t >= T_IMPACT and not fired_impact:
                blue_flash_local(px, LED_CAR, power=2.7)
                crackle(px, LED_CAR, spread=6, density=1.0, color='blue')
                fired_impact = True

                # Flash BLANCO GLOBAL (sin guardas)
                global_flash_white(hold_ms=550, power=1.0)
                white_hold_until = t + 0.50
                post_set_time    = white_hold_until
                continue

            # Post-efecto: FADE desde BLANCO → (Zona 3 naranja / resto azul profundo)
            if post_set_time is not None and t >= post_set_time:
                p = min(1.0, (t - post_set_time) / POST_FADE_S)  # 0=blanco, 1=objetivo
                white = WHITE
                target_blue   = scale(DEEP_BLUE,     2.4)
                target_orange = scale(ORANGE_INTENSE,2.0)

                px = [None] * N
                for i in range(N):
                    # Zona 3 (medio) en naranja; el resto (1,2,4) en azul
                    target = target_orange if i in ZONE3_SET else target_blue
                    px[i] = mix(white, target, p)

                if (t - post_set_time) > (POST_FADE_S + post_hold_s):
                    k = max(0.0, 1.0 - (t - (post_set_time + POST_FADE_S + post_hold_s)) / 0.6)
                    for i in range(N):
                        r, g, b = px[i]
                        px[i] = (r * k, g * k, b * k)

            # Efectos convergentes decorativos (post)
            if not fired_blue and t >= T_BLUE_SPARK:
                fired_blue = True
                blue_effect_start = t
            if fired_blue:
                elapsed_blue = t - blue_effect_start
                BLUE_SPARK_DURATION = max(0.1, T_ORANGE_SPARK - T_BLUE_SPARK)
                if elapsed_blue <= BLUE_SPARK_DURATION:
                    progress_blue = elapsed_blue / BLUE_SPARK_DURATION
                    apply_blue_converge_effect(px, progress_blue)

            if not fired_orange and t >= T_ORANGE_SPARK:
                fired_orange = True
                orange_effect_start = t

            if fired_orange:
                elapsed = t - orange_effect_start
                ORANGE_SPARK_DURATION = 1.0
                if elapsed <= ORANGE_SPARK_DURATION:
                    progress = elapsed / ORANGE_SPARK_DURATION
                    apply_orange_converge_effect(px, progress)

            # Enviar frame
            send_frame(px)
            time.sleep(1.0 / FPS)

        # fundido final suave
        for f in range(int(0.6 * FPS)):
            k = 1.0 - f / (0.6 * FPS)
            send_frame(frame_fill(scale(ELECTRIC_BLUE, 0.06 * k)))
            time.sleep(1.0 / FPS)
        send_frame(frame_fill((0, 0, 0)), duration=500)

    finally:
        cleanup()

# ========= CLI =========
def main():
    p = argparse.ArgumentParser(description="BTTF Torre del Reloj (132 LEDs, Zona1 añadida, rayo 101–132→69–61→55–54→42)")
    p.add_argument("--video", default=VIDEO_FILE_DEFAULT, help="Ruta al .mp4 (por defecto /home/pi/bttf.mp4)")
    p.add_argument("--clock-offset", type=float, default=0.0, help="Ajuste (s) rayo al reloj")
    p.add_argument("--car-offset", type=float, default=0.0, help="Ajuste (s) rayo al coche")
    args = p.parse_args()
    run_show_with_video(args.video, args.clock_offset, args.car_offset)

if __name__ == "__main__":
    main()
