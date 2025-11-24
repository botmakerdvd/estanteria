#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# regreso_al_futuro_torre_reloj_largo_refactored.py
# REFACTORIZADO FINAL (CORREGIDO): Timeline limpio y variables de Spark definidas.

import os, time, math, random, json, socket, subprocess, atexit, argparse, requests
from typing import List, Tuple

# --- IMPORTACIONES PROPIAS ---
from layout import * # Configuración de LEDs
from rf_control import RFManager # Gestión de Radiofrecuencia (incluye el GAP de seguridad)

# ========= CONFIG =========
VIDEO_FILE_DEFAULT = "/home/pi/bttflargo.mp4"
HOST       = "http://localhost:8090"
TOKEN      = None
PRIORITY   = 64
ORIGIN     = "bttf"
FPS        = 30
GAMMA      = 1.0
AUDIO_DEVICE = "alsa/hdmi:CARD=vc4hdmi,DEV=0"

# ========= TIMELINE BASE (Segundos) =========
T_CLOCK_BASE  = 139.2   
T_IMPACT_BASE = 143.5   
T_BLUE_SPARK_START  = 149.2
T_ORANGE_SPARK_BASE = 155.59

# Tiempos de RF (Definidos aquí para usarlos en el Timeline)
T_FALLO_MOTOR  = 40.23
T_PRUEBA_MOTOR = 49.27
T_ENCENDIDO    = 66.7
T_RUEDAS       = 127.53

# ========= PUNTOS CLAVE LEDs =========
LED_CLOCK = [54, 55]   
LED_CAR   = [42, 41]   

# ========= PATH DEL RAYO =========
PRE_PATH_1 = list(range(100, 132))            
PRE_PATH_2 = list(range(68, 59, -1))          
TRAVEL_PATH_TO_CAR = list(range(55, 40, -1))  

PRE_TOTAL_S = 2.4       
PRE_HOLD_CLOCK = 0.18   

# ========= HYPERION =========
headers = {"Content-Type": "application/json"}
if TOKEN: headers["Authorization"] = f"Bearer {TOKEN}"

def clamp(x): return max(0, min(255, int(x)))
def lerp(a, b, t): return a + (b - a) * t
def mix(c1, c2, t): return (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))
def scale(c, k): return (c[0] * k, c[1] * k, c[2] * k)

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
    else:                add(px, i, scale(ELECTRIC_BLUE, val * 0.8)) 

def white_flash_local(px, indices, power=2.2, force=False):
    for i in indices:
        if force or white_allowed(i):
            add(px, i, scale(WHITE, 2.2 * power))
            if i - 1 >= 0: add(px, i - 1, scale(WHITE, 0.7 * power))
            if i + 1 < N: add(px, i + 1, scale(WHITE, 0.7 * power))
        else:
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
    if not path: return
    head_idx = int(max(0, min(len(path) - 1, round(head_pos * (len(path) - 1)))))
    for j in range(tail):
        idx = head_idx - j
        if idx < 0: break
        led = path[idx]
        fade = max(0.0, 1.0 - j / max(1, tail))
        
        effective_color = WHITE if color == 'white' and white_allowed(led) else ELECTRIC_BLUE
        
        add(px, led, scale(effective_color, head_gain * fade))
        if led - 1 >= 0: add(px, led - 1, scale(effective_color, 0.45 * fade))
        if led + 1 < N: add(px, led + 1, scale(effective_color, 0.45 * fade))

def apply_converge_effect(px, progress, color, crackle_color, tail=5, bloom_base=0.35, bloom_amp=0.25, head_gain=2.4, center_gain=1.8):
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

def storm_clouds_zone1(px, density: float = 0.14):
    if not ZONE1: return
    if random.random() < density:
        size = random.randint(2, 5)
        center = random.choice(ZONE1)
        for j in range(-size, size + 1):
            idx = center + j
            if idx in ZONE1_SET: 
                _add_white_guarded(px, idx, 1.4 * (1 - abs(j) / (size + 1)))

def global_flash_white(hold_ms=550, power=1.0):
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

    # Cálculo de tiempos finales
    T_CLOCK  = T_CLOCK_BASE  + clock_offset
    T_IMPACT = T_IMPACT_BASE + car_offset

    # CORRECCIÓN: Definición de variables Spark
    T_BLUE_SPARK   = T_BLUE_SPARK_START
    T_ORANGE_SPARK = T_ORANGE_SPARK_BASE

    # --- DEFINICIÓN DE LA COLA DE EVENTOS RF (TIMELINE) ---
    rf_timeline = [
        # Inicio
        (2.0, "front"),
        (2.0, "rear"), 
        
        # Fallo de motor
        (T_FALLO_MOTOR, "front"), 
        (T_FALLO_MOTOR, "rear"), 
        
        # Encendido
        (T_ENCENDIDO, "front"),
        (T_ENCENDIDO, "rear"),
        
        # Ruedas
        (T_RUEDAS,       "wheels"),
        (T_RUEDAS + 1.5, "wheels"), 
        
        # Impacto
        (T_IMPACT, "blue_front"),
        (T_IMPACT, "blue_rear")
    ]
    
    rf_timeline.sort(key=lambda x: x[0])
    next_rf_idx = 0 

    fired_clock = False
    fired_travel = False
    fired_impact = False
    fired_blue = False
    fired_orange = False
    pre_start_time = None
    travel_start_time = None
    white_hold_until  = None
    post_set_time     = None
    post_hold_s       = 4.0
    POST_FADE_S       = 1.8
    
    rf = RFManager() 

    try:
        while True:
            if mpv_proc.poll() is not None:
                break

            t = mpv_get_prop("time-pos")
            if t is None:
                time.sleep(1.0 / FPS)
                continue

            # --- LÓGICA RF: COLA DE EVENTOS ---
            while next_rf_idx < len(rf_timeline) and t >= rf_timeline[next_rf_idx][0]:
                event_time, code_name = rf_timeline[next_rf_idx]
                rf.send(code_name)
                next_rf_idx += 1

            # --- RESTO DE EFECTOS VISUALES (LEDs) ---
            if white_hold_until is not None and t < white_hold_until:
                send_frame(frame_fill(scale(WHITE, 2.5)))
                time.sleep(1.0 / FPS)
                continue

            px = idle_ambient(phase=(t or 0) * 0.25)

            if t < (T_CLOCK - 0.05):
                storm_clouds_zone1(px, density=0.14)

            # Rayo (Prefase)
            if t >= (T_CLOCK - PRE_TOTAL_S) and t < T_CLOCK:
                if pre_start_time is None:
                    pre_start_time = t
                    white_flash_local(px, [100, 101], power=2.0) 
                p = max(0.0, min(1.0, (t - pre_start_time) / PRE_TOTAL_S))
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
                    draw_along_path(px, PRE_PATH_2, head_pos2, tail=8, color='blue', head_gain=2.0)

            # Golpe Reloj
            if t >= T_CLOCK and not fired_clock:
                white_flash_local(px, LED_CLOCK, power=2.3, force=True)
                crackle(px, LED_CLOCK, spread=5, density=0.9, color='white')
                fired_clock = True
                travel_start_time = t + PRE_HOLD_CLOCK 

            # Viaje al Coche
            if fired_clock and not fired_travel:
                dur = max(0.01, T_IMPACT - travel_start_time)
                u = 0.0 if dur == 0 else min(1.0, max(0.0, (t - travel_start_time) / dur))
                draw_along_path(px, TRAVEL_PATH_TO_CAR, u, tail=10, color='blue', head_gain=2.1)
                if u >= 1.0:
                    fired_travel = True
            
            # Impacto Visual
            if t >= T_IMPACT and not fired_impact:
                blue_flash_local(px, LED_CAR, power=2.7)
                crackle(px, LED_CAR, spread=6, density=1.0, color='blue')
                fired_impact = True
                global_flash_white(hold_ms=550, power=1.0)
                white_hold_until = t + 0.50
                post_set_time    = white_hold_until
                continue

            # Post-efecto
            if post_set_time is not None and t >= post_set_time:
                p = min(1.0, (t - post_set_time) / POST_FADE_S) 
                white = WHITE
                target_blue   = scale(DEEP_BLUE,     2.4)
                target_orange = scale(ORANGE_INTENSE,2.0)

                px = [None] * N
                for i in range(N):
                    target = target_orange if i in ZONE3_SET else target_blue
                    px[i] = mix(white, target, p)

                if (t - post_set_time) > (POST_FADE_S + post_hold_s):
                    k = max(0.0, 1.0 - (t - (post_set_time + POST_FADE_S + post_hold_s)) / 0.6)
                    for i in range(N):
                        r, g, b = px[i]
                        px[i] = (r * k, g * k, b * k)

            # Efectos decorativos finales (USAN T_BLUE_SPARK y T_ORANGE_SPARK)
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
                if elapsed <= 1.0:
                    progress = elapsed / 1.0
                    apply_orange_converge_effect(px, progress)

            send_frame(px)
            time.sleep(1.0 / FPS)

        # Fundido final
        for f in range(int(0.6 * FPS)):
            k = 1.0 - f / (0.6 * FPS)
            send_frame(frame_fill(scale(ELECTRIC_BLUE, 0.06 * k)))
            time.sleep(1.0 / FPS)
        send_frame(frame_fill((0, 0, 0)), duration=500)

    finally:
        cleanup()
        rf.cleanup()

# ========= CLI =========
def main():
    p = argparse.ArgumentParser(description="BTTF Torre del Reloj (Timeline RF Refactorizado)")
    p.add_argument("--video", default=VIDEO_FILE_DEFAULT, help="Ruta al .mp4")
    p.add_argument("--clock-offset", type=float, default=0.0, help="Ajuste (s) rayo al reloj")
    p.add_argument("--car-offset", type=float, default=0.0, help="Ajuste (s) rayo al coche")
    args = p.parse_args()
    run_show_with_video(args.video, args.clock_offset, args.car_offset)

if __name__ == "__main__":
    main()