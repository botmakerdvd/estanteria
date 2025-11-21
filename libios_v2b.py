#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# libios_show_v2b.py — Disparos también en el nuevo estante (Zona 1)
# Cambios respecto a v2:
# - Los fogonazos/disparos (manuales y AUTO_SHOTS) ahora afectan a TODAS las zonas (1..4).
# - En ráfaga Doc y impactos añadimos chisporroteo también en Zona 1 para que “salte” arriba del todo.
#
# Resto igual que v2 (132 LEDs, zonas 1..4, túneles extendidos, guardia de blanco en salto, etc).

import os, time, math, random, json, socket, subprocess, atexit, argparse, requests
from typing import List

# ========= CONFIG =========
VIDEO_FILE_DEFAULT = "/home/pi/libios.mp4"
HOST       = "http://localhost:8090"
TOKEN      = None
PRIORITY   = 64
ORIGIN     = "bttf_libios"
FPS        = 30
GAMMA      = 1.0
AUDIO_DEVICE = "alsa/hdmi:CARD=vc4hdmi,DEV=0"

# ========= LAYOUT (132 LEDs) =========
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

# Nuevo estante (Zona 1) — 36 LEDs (0-based 96..131)
Z1_R = list(range(96, 105))      # derecha (abajo→arriba)
Z1_T = list(range(105, 123))     # centro (derecha→izquierda)
Z1_L = list(range(123, 132))     # izquierda (arriba→abajo)

N = 132

ZONE1 = Z1_R + Z1_T + Z1_L
ZONE2 = INDEX["T_L"] + INDEX["T_T"] + INDEX["T_R"]
ZONE3 = INDEX["M_L"] + INDEX["M_T"] + INDEX["M_R"]
ZONE4 = INDEX["B_L"] + INDEX["B_T"] + INDEX["B_R"]

ZONE1_SET, ZONE2_SET, ZONE3_SET, ZONE4_SET = set(ZONE1), set(ZONE2), set(ZONE3), set(ZONE4)

TOP_ZONE, MIDDLE_ZONE, BOTTOM_ZONE = ZONE2, ZONE3, ZONE4

FULL_PATH = []
for name,_ in SEGMENTS_96:
    FULL_PATH += INDEX[name]
FULL_PATH += Z1_R + Z1_T + Z1_L

# ========= COLOR/UTILS =========
def clamp(x): return max(0, min(255, int(x)))
def lerp(a, b, t): return a + (b - a) * t
def mix(c1, c2, t): return (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))
def scale(c, k): return (c[0]*k, c[1]*k, c[2]*k)

WHITE          = (255,255,255)
ELECTRIC_BLUE  = (150,200,255)
DEEP_BLUE      = (30, 90,200)
ORANGE_INTENSE = (255, 80,  0)
AMBER_SOFT     = (255,140, 40)
RED_SIREN      = (255,  0, 20)
BLUE_SIREN     = (  0, 80,255)
GREEN_CIRCUITS = ( 60,255, 80)
YELLOW_WARM    = (255,200, 40)

MIN_WHITE_INDEX = 96
def white_allowed(i: int) -> bool: return i >= MIN_WHITE_INDEX

def apply_gamma(c):
    if GAMMA == 1.0: return c
    r,g,b = c
    gfun = lambda v: 255*((v/255.0)**GAMMA)
    return (gfun(r), gfun(g), gfun(b))

def pack(pixels):
    flat=[]
    for r,g,b in pixels:
        r,g,b = apply_gamma((r,g,b))
        flat += [clamp(r),clamp(g),clamp(b)]
    return flat

headers = {"Content-Type":"application/json"}
if TOKEN: headers["Authorization"]=f"Bearer {TOKEN}"

def send_frame(pixels, duration=-1):
    payload = {"command":"color","color":pack(pixels),
               "priority":PRIORITY,"origin":ORIGIN,"duration":duration}
    try:
        requests.post(f"{HOST}/json-rpc", headers=headers, json=payload, timeout=2)
    except Exception:
        pass

def frame_fill(c): return [c]*N
def add(px, i, c):
    if 0<=i<N:
        r,g,b = px[i]; cr,cg,cb = c
        px[i]=(r+cr,g+cg,b+cb)

# ========= EFECTOS =========
def idle_ambient(t):
    k = 0.06 + 0.05*math.sin(t*0.6)
    return frame_fill(scale(DEEP_BLUE, k))

def crackle(px, indices, spread=2, density=0.7, base=(255,255,255), mix_with=(0,0,0), mix_amt=0.2):
    for c in indices:
        for j in range(-spread, spread+1):
            i = c + j
            if 0<=i<N and random.random() < density*(1 - abs(j)/(spread+1)):
                col = mix(base, mix_with, mix_amt)
                add(px, i, col)

def muzzle_blast_white(px, zones: List[List[int]], width=5, density=0.95):
    for zone in zones:
        if not zone: continue
        centers = random.sample(zone, k=max(1, len(zone)//12))
        for c in centers:
            for j in range(-width, width+1):
                i = c+j
                if 0<=i<N and random.random()<density*(1 - abs(j)/(width+1)):
                    add(px, i, scale(WHITE, 2.5*(1-abs(j)/(width+1))))
                    add(px, i, scale(RED_SIREN, 0.25*(1-abs(j)/(width+1))))

def sweep_path(px, path: List[int], color, width=7, pos=0.0, gain=1.8):
    m=len(path)
    if m==0: return
    head = int(lerp(0, m-1, pos))
    for k in range(width+1):
        idx = head - k
        if 0 <= idx < m:
            led = path[idx]
            fade = max(0.0, 1.0 - k/width)
            add(px, led, scale(color, gain*fade))

def tunnel_effect(px, path: List[int], speed_phase: float, strength=1.6, tail=12, color=ELECTRIC_BLUE):
    m = len(path)
    if m==0: return
    head_pos = (speed_phase % 1.0) * (m-1)
    head = int(head_pos)
    for j in range(tail):
        idx = head - j
        if 0 <= idx < m:
            led = path[idx]
            k = max(0.0, 1.0 - j/tail)
            add(px, led, scale(color, strength*k))
            if led-1>=0: add(px, led-1, scale(color, 0.45*k))
            if led+1<N:  add(px, led+1, scale(color, 0.45*k))

def pulse_zone(px, zone, color_a, color_b, phase, gain=1.0):
    k = 0.5 + 0.5*math.sin(phase*2*math.pi)
    col = mix(color_a, color_b, k)
    for i in zone: add(px, i, scale(col, gain))

def one_frame_white_guarded():
    px = frame_fill((0,0,0))
    for i in range(N):
        if white_allowed(i): add(px, i, scale(WHITE, 2.5))
        else:                add(px, i, scale(ELECTRIC_BLUE, 2.2))
    send_frame(px, duration=int(1000/FPS))

def police_sirens_fullrun(px, t, t0, duration=3.0):
    u = max(0.0, min(1.0, (t - t0)/duration))
    speed = 0.8 + 1.6*u
    phase = ((t - t0) * speed) % 1.0
    toggle = int((t - t0) * 12.5) % 2
    colA = BLUE_SIREN if toggle==0 else RED_SIREN
    colB = RED_SIREN  if toggle==0 else BLUE_SIREN
    sweep_path(px, FULL_PATH, colA, width=7, pos=phase, gain=1.8)
    sweep_path(px, list(reversed(FULL_PATH)), colB, width=7, pos=phase, gain=1.8)
    pulse_zone(px, TOP_ZONE, BLUE_SIREN, RED_SIREN, phase=t*1.1, gain=0.15)

# ========= SPEED FEEL =========
SPEED_STROBE_BASE_HZ = 6.0
SPEED_STROBE_MAX_HZ  = 22.0
TRAIL_LEN_BASE       = 12
TRAIL_LEN_MAX        = 28
TUNNEL_GAIN_BASE     = 1.6
TUNNEL_GAIN_MAX      = 3.0
BLUR_DECAY           = 0.45

prev_px = None

def roadside_markers(px, path, t, v, dash_gap=6):
    m = len(path)
    if m == 0: return
    speed = 0.6 + 3.0*v
    phase = (t*speed) % 1.0
    step  = max(3, int(8 - 5*v))
    for k in range(0, m, step):
        idx = int((k + phase*(step)) % m)
        led = path[idx]
        add(px, led, scale(WHITE, 1.6 + 1.2*v))
        if led-1 >= 0: add(px, led-1, scale(AMBER_SOFT, 0.6 + 0.6*v))
        if led+1 < N:  add(px, led+1, scale(AMBER_SOFT, 0.6 + 0.6*v))

def warp_strobe(px, t, v):
    hz = SPEED_STROBE_BASE_HZ + (SPEED_STROBE_MAX_HZ - SPEED_STROBE_BASE_HZ)*v
    on = (int(t*hz) % 2) == 0
    if on:
        k = 0.6 + 0.6*v
        for i in range(N):
            add(px, i, scale(WHITE, k))

def parallax_tunnel_bundle(px, t, v, accel_phase, side_path, top_path, right_path, color):
    tail = int(TRAIL_LEN_BASE + (TRAIL_LEN_MAX - TRAIL_LEN_BASE)*v)
    gain = TUNNEL_GAIN_BASE + (TUNNEL_GAIN_MAX - TUNNEL_GAIN_BASE)*v
    tunnel_effect(px, side_path,  accel_phase*1.00, strength=gain*1.00, tail=tail, color=color)
    tunnel_effect(px, top_path,   accel_phase*1.10, strength=gain*1.10, tail=tail, color=color)
    tunnel_effect(px, right_path, accel_phase*1.18, strength=gain*1.05, tail=tail, color=color)

# ========= TIMELINE =========
def s_f(sec, frame): return sec + frame/24.0
T_VAN_APPEAR      = s_f(23,5)
T_SHOTS_START     = s_f(29,0)
SHOT_IMPACTS      = [s_f(30,15), s_f(31,12), s_f(38,16), s_f(41,16), s_f(44,4)]
DOC_BURST_START   = s_f(53,15)
DOC_BURST_END     = s_f(56,17)
GUN_JAM           = 74.0
MARTY_TO_DELOREAN = 80.0
DELOREAN_START    = s_f(94,10)
TIME_CIRCUITS_ON  = s_f(105,2) - 0.4
TIME_CIRCUITS_LEN = 3.0
ACCEL1_START      = 131.0
ACCEL1_END        = s_f(136,10)
MORTAR_AIM        = 150.0
ACCEL2_START      = s_f(160,4)
JUMP_88MPH        = 176.0
JUMP_FLASH_END    = 178.5
SHOW_END_APPROX   = s_f(181,0)

AUTO_SHOTS = [
    30.52, 30.66, 30.87, 31.01, 31.14, 31.28, 37.44, 37.87, 38.08, 38.75,
    38.87, 39.49, 43.16, 43.30, 43.58, 43.97, 46.67, 53.42, 53.63, 53.80,
    53.97, 54.12, 54.27, 54.43, 54.59, 54.72, 54.89, 55.01, 55.18, 55.39,
    55.54, 55.74, 55.91, 56.07, 56.26, 56.41, 56.60, 56.74, 57.67, 58.06,
    63.54, 63.74, 63.92, 64.10, 64.26, 64.45, 64.64, 64.84, 65.02,
    103.90, 112.63, 112.78, 112.92, 116.67, 118.60, 120.25, 122.80,
    149.57, 159.86, 163.60, 163.72, 164.80, 169.80, 175.72, 176.70,
    176.86, 177.03, 177.16, 177.29, 177.41, 177.53, 179.21, 179.33,
    179.55, 179.68
]

# ========= MPV IPC =========
SOCK_PATH = "/tmp/mpv-libios.sock"
MPV_LOG   = "/tmp/mpv-libios.log"
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
        send_frame(frame_fill((0,0,0)), duration=500)
    except: pass
atexit.register(cleanup)

def start_mpv(video_path):
    global mpv_proc
    if os.path.exists(SOCK_PATH):
        try: os.remove(SOCK_PATH)
        except: pass
    cmd = [
        "mpv", video_path,
        "--fs","--no-osc","--keep-open=no",
        f"--input-ipc-server={SOCK_PATH}",
        "--gpu-context=drm",
        "--ao=alsa","--audio-samplerate=48000",
        "--volume=100","--mute=no",
    ]
    if AUDIO_DEVICE:
        cmd.append(f"--audio-device={AUDIO_DEVICE}")
    logf = open(MPV_LOG, "w")
    mpv_proc = subprocess.Popen(cmd, stdout=logf, stderr=logf)

def connect_ipc(timeout=10.0):
    t0=time.time()
    while time.time()-t0<timeout:
        if os.path.exists(SOCK_PATH): break
        time.sleep(0.05)
    global ipc_sock
    t0=time.time()
    while time.time()-t0<timeout:
        try:
            s=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(SOCK_PATH)
            ipc_sock=s
            return
        except Exception:
            time.sleep(0.05)
    raise RuntimeError("No se pudo conectar al socket IPC de mpv")

def mpv_get_prop(prop: str, timeout=0.2):
    req={"command":["get_property", prop],"request_id":1}
    if not ipc_sock: return None
    try:
        ipc_sock.sendall((json.dumps(req)+"\n").encode("utf-8"))
        ipc_sock.settimeout(timeout)
        data=b""
        while True:
            chunk=ipc_sock.recv(4096)
            if not chunk: break
            data+=chunk
            if b"\n" in data:
                lines=data.split(b"\n")
                for line in lines:
                    if not line.strip(): continue
                    try:
                        msg=json.loads(line.decode("utf-8"))
                        if msg.get("request_id")==1 and msg.get("error")=="success":
                            return msg.get("data")
                    except: continue
                break
    except Exception:
        return None
    return None

# ========= COREOGRAFÍA =========
def run_show(video_path):
    global prev_px
    random.seed()
    start_mpv(video_path)
    connect_ipc()

    fired = set()
    accel_phase = 0.0
    accel_speed = 0.0

    SIDE_PATH  = INDEX["B_L"] + INDEX["M_L"] + INDEX["T_L"] + Z1_L
    TOP_PATH   = TOP_ZONE + Z1_T
    RIGHT_PATH = INDEX["B_R"] + INDEX["M_R"] + INDEX["T_R"] + Z1_R

    try:
        while True:
            if mpv_proc.poll() is not None:
                break
            t = mpv_get_prop("time-pos")
            if t is None:
                time.sleep(1.0/FPS)
                continue

            px = idle_ambient(t or 0.0)

            # 1) Entrada van: sirena
            if T_VAN_APPEAR <= t < (T_VAN_APPEAR+3.0):
                police_sirens_fullrun(px, t, T_VAN_APPEAR, duration=3.0)

            # 2) Inicio disparos: ahora en TODAS las zonas (1..4)
            if t >= T_SHOTS_START and "shots_start" not in fired:
                fired.add("shots_start")
                muzzle_blast_white(px, [ZONE4, ZONE3, ZONE2, ZONE1], width=5, density=0.95)

            # Impactos puntuales + chisporroteo también en Zona 1
            for k,imp_t in enumerate(SHOT_IMPACTS):
                key=f"impact_{k}"
                if t >= imp_t and key not in fired:
                    fired.add(key)
                    muzzle_blast_white(px, [ZONE4, ZONE3, ZONE2, ZONE1], width=5, density=0.95)
                    crackle(px, (TOP_ZONE[::3] + ZONE1[::4]), spread=2, density=0.8, base=WHITE, mix_with=(0,0,0), mix_amt=0.15)

            # 3) Disparos adicionales AUTO_SHOTS en todas las zonas
            for ds in AUTO_SHOTS:
                key = f"audshot_{ds:.2f}"
                if t >= ds and key not in fired:
                    fired.add(key)
                    muzzle_blast_white(px, [ZONE4, ZONE3, ZONE2, ZONE1], width=5, density=0.95)
                    crackle(px, (TOP_ZONE[::2] + ZONE1[::3]), spread=3, density=0.85, base=WHITE, mix_with=(0,0,0), mix_amt=0.10)

            # 4) Doc acribillado — incluye ahora Zona 1 en el chisporroteo
            if DOC_BURST_START <= t <= DOC_BURST_END:
                if int(t*24)%2==0:
                    muzzle_blast_white(px, [ZONE4, ZONE3, ZONE2, ZONE1], width=5, density=0.95)
                crackle(px, (TOP_ZONE[::2] + ZONE1[::3]), spread=3, density=0.85, base=WHITE, mix_with=(0,0,0), mix_amt=0.10)

            # 5) Marty + motor en Zona 3
            if t >= MARTY_TO_DELOREAN and "marty_in" not in fired:
                fired.add("marty_in")
                for i in range(N): add(px, i, scale(ELECTRIC_BLUE, 0.8))
            if t >= DELOREAN_START:
                accel_speed = max(accel_speed, 0.35)
                if not (TIME_CIRCUITS_ON <= t < (TIME_CIRCUITS_ON + TIME_CIRCUITS_LEN)):
                    pulse_zone(px, MIDDLE_ZONE, AMBER_SOFT, YELLOW_WARM, phase=t*0.75, gain=0.35)

            # 6) Time Circuits (2–4) — Zona 1 se mantiene fuera
            if TIME_CIRCUITS_ON <= t < (TIME_CIRCUITS_ON + TIME_CIRCUITS_LEN):
                pulse_zone(px, TOP_ZONE,    RED_SIREN,      RED_SIREN,      phase=t*0.5,      gain=0.45)
                pulse_zone(px, MIDDLE_ZONE, GREEN_CIRCUITS, GREEN_CIRCUITS, phase=t*0.5+0.33, gain=0.35)
                pulse_zone(px, BOTTOM_ZONE, AMBER_SOFT,     AMBER_SOFT,     phase=t*0.5+0.66, gain=0.30)

            # 7) Aceleración 1
            if ACCEL1_START <= t <= ACCEL1_END:
                u = (t - ACCEL1_START)/max(0.1, (ACCEL1_END - ACCEL1_START))
                v = max(0.0, min(1.0, u))
                accel_speed = max(accel_speed, 0.6 + 0.8*v)
                accel_phase += 0.035 + 0.12*accel_speed

                color_flux = mix(AMBER_SOFT, ORANGE_INTENSE, 0.5 + 0.5*math.sin(t*2.0))

                parallax_tunnel_bundle(px, t, v, accel_phase, 
                                       INDEX["B_L"] + INDEX["M_L"] + INDEX["T_L"] + Z1_L,
                                       TOP_ZONE + Z1_T,
                                       INDEX["B_R"] + INDEX["M_R"] + INDEX["T_R"] + Z1_R,
                                       color_flux)

                roadside_markers(px, INDEX["B_L"] + INDEX["M_L"] + INDEX["T_L"] + Z1_L,  t, v)
                roadside_markers(px, TOP_ZONE + Z1_T,   t, v)
                roadside_markers(px, INDEX["B_R"] + INDEX["M_R"] + INDEX["T_R"] + Z1_R, t, v)

                warp_strobe(px, t, v*0.7)

                crackle(px, list(range(0, N, 4)), spread=2, density=0.30,
                        base=color_flux, mix_with=WHITE, mix_amt=0.20)

                if prev_px is not None:
                    for i in range(N):
                        r,g,b = px[i]; pr,pg,pb = prev_px[i]
                        px[i] = (r + BLUR_DECAY*pr, g + BLUR_DECAY*pg, b + BLUR_DECAY*pb)
                prev_px = px[:]

            # 8) Mortero/alarma
            if MORTAR_AIM <= t < MORTAR_AIM+3.0:
                phase = (t-MORTAR_AIM)
                ring = 0.5 + 0.5*math.sin(phase*4.0*math.pi)
                for i in TOP_ZONE:    add(px, i, scale(RED_SIREN, 0.7*ring))
                for i in MIDDLE_ZONE: add(px, i, scale(RED_SIREN, 0.35*ring))
                for i in BOTTOM_ZONE: add(px, i, scale(RED_SIREN, 0.25*ring))

            # 9) Aceleración final
            if ACCEL2_START <= t < JUMP_88MPH:
                v = (t - ACCEL2_START)/max(0.1, (JUMP_88MPH - ACCEL2_START))
                v = max(0.0, min(1.0, v))
                accel_speed = max(accel_speed, 1.2 + 2.2*v)
                accel_phase += 0.05 + 0.25*accel_speed

                color_flux = mix(AMBER_SOFT, ORANGE_INTENSE, 0.5 + 0.5*math.sin(t*3.0))

                parallax_tunnel_bundle(px, t, v, accel_phase, 
                                       INDEX["B_L"] + INDEX["M_L"] + INDEX["T_L"] + Z1_L,
                                       TOP_ZONE + Z1_T,
                                       INDEX["B_R"] + INDEX["M_R"] + INDEX["T_R"] + Z1_R,
                                       color_flux)

                roadside_markers(px, INDEX["B_L"] + INDEX["M_L"] + INDEX["T_L"] + Z1_L,  t, v)
                roadside_markers(px, TOP_ZONE + Z1_T,   t, v)
                roadside_markers(px, INDEX["B_R"] + INDEX["M_R"] + INDEX["T_R"] + Z1_R, t, v)

                warp_strobe(px, t, v)

                crackle(px, list(range(0, N, 3)), spread=2, density=0.25+0.5*v,
                        base=color_flux, mix_with=WHITE, mix_amt=0.25)

                if prev_px is not None:
                    for i in range(N):
                        r,g,b = px[i]; pr,pg,pb = prev_px[i]
                        px[i] = (r + BLUR_DECAY*pr, g + BLUR_DECAY*pg, b + BLUR_DECAY*pb)
                prev_px = px[:]

            # 10) Salto temporal — blanco guardado (solo Zona 1)
            if JUMP_88MPH <= t <= JUMP_FLASH_END:
                prev_px = None
                p=(t-JUMP_88MPH)/max(0.01, (JUMP_FLASH_END-JUMP_88MPH))
                if int(t*24)%2==0:
                    for i in range(N):
                        add(px, i, scale(ELECTRIC_BLUE, 3.2*(0.8+0.4*math.sin(6.28*p))))
                else:
                    for i in range(N):
                        if white_allowed(i): add(px, i, scale(WHITE, 2.5))
                        else:                add(px, i, scale(ELECTRIC_BLUE, 2.2))
                if abs(t - JUMP_88MPH) < (1.0/FPS) and "jump_white" not in fired:
                    fired.add("jump_white")
                    one_frame_white_guarded()

            send_frame(px)
            time.sleep(1.0/FPS)

            if t and t > SHOW_END_APPROX:
                break

        for f in range(int(0.8*FPS)):
            k = 1.0 - f/(0.8*FPS)
            send_frame(frame_fill(scale(ELECTRIC_BLUE, 0.06*k)))
            time.sleep(1.0/FPS)
        send_frame(frame_fill((0,0,0)), duration=600)

    finally:
        cleanup()

# ========= CLI =========
def main():
    p = argparse.ArgumentParser(description="Persecución con los libios — v2b: disparos en todas las zonas (1..4) — 132 LEDs")
    p.add_argument("--video", default=VIDEO_FILE_DEFAULT, help="Ruta al .mp4 (por defecto /home/pi/libios.mp4)")
    args = p.parse_args()
    run_show(args.video)

if __name__ == "__main__":
    main()
