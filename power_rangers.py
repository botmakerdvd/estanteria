# pip install requests
import requests, time, math, random
from itertools import chain

# ===== CONFIG =====
HOST     = "http://localhost:8090"
TOKEN    = None
PRIORITY = 64
ORIGIN   = "sFX3_rangers_v3b"
FPS      = 12
GAMMA    = 1.0
BG_DIM   = (4,4,4)

# ===== LAYOUT (Zonas 1..4 con L/T/R) =====
LEN = {
    "Z4_L": 6, "Z4_T": 18, "Z4_R": 6,
    "Z3_R": 6, "Z3_T": 18, "Z3_L": 6,
    "Z2_L": 9, "Z2_T": 18, "Z2_R": 9,
}
SEGMENT_ORDER = ["Z4_L","Z4_T","Z4_R","Z3_R","Z3_T","Z3_L","Z2_L","Z2_T","Z2_R"]
REVERSED = {"Z4_R": True, "Z3_L": True, "Z3_T": True, "Z2_R": True}

INDEX = {}
cursor = 0
for key in SEGMENT_ORDER:
    L = LEN[key]
    ids = list(range(cursor, cursor+L))
    if REVERSED.get(key, False): ids.reverse()
    INDEX[key] = ids
    cursor += L  # -> 96

# ZONA 1 (nuevo estante) 0-based 96..131
# R (97–105 1-based): abajo→arriba
INDEX["Z1_R"] = list(range(96, 105))
# T (106–123 1-based): derecha→izquierda
INDEX["Z1_T"] = list(range(105, 123))[::-1]
# L (124–132 1-based): **CORREGIDO** queremos que la columna ascienda,
# así que el orden del chain debe ser de abajo→arriba. Como físicamente es arriba→abajo,
# invertimos para el recorrido lógico de subida.
INDEX["Z1_L"] = list(range(123, 132))[::-1]

N = 132

Z = {
    1: {"L": INDEX["Z1_L"], "T": INDEX["Z1_T"], "R": INDEX["Z1_R"]},
    2: {"L": INDEX["Z2_L"], "T": INDEX["Z2_T"], "R": INDEX["Z2_R"]},
    3: {"L": INDEX["Z3_L"], "T": INDEX["Z3_T"], "R": INDEX["Z3_R"]},
    4: {"L": INDEX["Z4_L"], "T": INDEX["Z4_T"], "R": INDEX["Z4_R"]},
}

LEFT_CHAIN  = Z[4]["L"] + Z[3]["L"] + Z[2]["L"] + Z[1]["L"]
RIGHT_CHAIN = Z[4]["R"] + Z[3]["R"] + Z[2]["R"] + Z[1]["R"]
TOPS_CHAIN  = Z[4]["T"] + Z[3]["T"] + Z[2]["T"] + Z[1]["T"]

PATH = Z[4]["L"] + Z[4]["T"] + Z[4]["R"] + \
       Z[3]["R"] + Z[3]["T"] + Z[3]["L"] + \
       Z[2]["L"] + Z[2]["T"] + Z[2]["R"] + \
       Z[1]["R"] + Z[1]["T"] + Z[1]["L"]

# ===== COLOR/UTIL =====
def clamp(x): return max(0, min(255, int(x)))
def lerp(a,b,t): return a + (b-a)*t
def mix(c1,c2,t): return (lerp(c1[0],c2[0],t), lerp(c1[1],c2[1],t), lerp(c1[2],c2[2],t))
def scale(c,k):   return (c[0]*k, c[1]*k, c[2]*k)

WHITE = (255,255,255)

RANGERS = {
    "RED":    ((255, 20, 20), WHITE),
    "BLUE":   ((  0,120,255), WHITE),
    "YELLOW": ((255,220,  0), WHITE),
    "PINK":   ((255,  0,200), WHITE),
    "GREEN":  ((  0,255, 80), WHITE),
    "WHITE":  (WHITE,         WHITE),
    "BLACK":  ((  0,  0,  0), WHITE),
}
ORDER = ["RED","BLUE","YELLOW","PINK","GREEN","WHITE","BLACK"]

headers = {"Content-Type":"application/json"}
if TOKEN: headers["Authorization"] = f"Bearer {TOKEN}"

def apply_gamma(c):
    if GAMMA == 1.0: return c
    r,g,b = c
    gfun = lambda v: 255 * ((v/255.0) ** GAMMA)
    return (gfun(r), gfun(g), gfun(b))

def pack(pixels):
    flat=[]
    for r,g,b in pixels:
        r,g,b = apply_gamma((r,g,b))
        flat += [clamp(r), clamp(g), clamp(b)]
    return flat

def send_frame(pixels, duration=-1):
    payload = {"command":"color","color":pack(pixels),
               "priority":PRIORITY,"origin":ORIGIN,"duration":duration}
    try:
        requests.post(f"{HOST}/json-rpc", headers=headers, json=payload, timeout=5)
    except Exception:
        pass

def frame_fill(c): return [c]*N
def add(px, i, c):
    if 0<=i<N:
        r,g,b = px[i]; cr,cg,cb = c
        px[i] = (r+cr, g+cg, b+cb)

# ===== EFECTOS (idénticos a v3) =====
def vortex(center=(0.0,0.20), base=(0,0,255), accent=WHITE, seconds=1.2, spin=2.2):
    coords = [(0.0,0.0)]*N
    def set_coords(ids, x0,y0,x1,y1):
        L=len(ids)
        for k,idx in enumerate(ids):
            t = 0 if L==1 else k/(L-1)
            coords[idx] = (lerp(x0,x1,t), lerp(y0,y1,t))
    set_coords(Z[4]["L"], -1.0,-1.0, -1.0,-0.33)
    set_coords(Z[4]["R"], +1.0,-1.0, +1.0,-0.33)
    set_coords(Z[4]["T"], -0.9,-0.33, +0.9,-0.33)
    set_coords(Z[3]["L"], -1.0,-0.1, -1.0,+0.33)
    set_coords(Z[3]["R"], +1.0,-0.1, +1.0,+0.33)
    set_coords(Z[3]["T"], -0.9,+0.12, +0.9,+0.12)
    set_coords(Z[2]["L"], -1.0,+0.6, -1.0,+1.0)
    set_coords(Z[2]["R"], +1.0,+0.6, +1.0,+1.0)
    set_coords(Z[2]["T"], -0.9,+0.85, +0.9,+0.85)
    set_coords(Z[1]["L"], -1.0,+1.05, -1.0,+1.30)
    set_coords(Z[1]["R"], +1.0,+1.05, +1.0,+1.30)
    set_coords(Z[1]["T"], -0.9,+1.25, +0.9,+1.25)

    frames=int(FPS*seconds); cx,cy=center
    for f in range(frames):
        t=f/frames; px=frame_fill((0,0,0))
        for i,(x,y) in enumerate(coords):
            dx,dy=x-cx,y-cy; ang=(math.atan2(dy,dx)+math.pi)/(2*math.pi)
            ring=math.hypot(dx,dy); phase=(ang+spin*t)%1.0
            k=max(0.0,1.0-ring*1.2)*(0.4+0.6*phase)
            col=mix(base,accent,0.3+0.7*phase)
            add(px,i,scale(col,k))
        send_frame(px); time.sleep(1/FPS)

def volumetric_beam(color, seconds=0.9):
    chains = [(Z[4]["L"], Z[4]["T"], Z[4]["R"]),
              (Z[3]["L"], Z[3]["T"], Z[3]["R"]),
              (Z[2]["L"], Z[2]["T"], Z[2]["R"]),
              (Z[1]["L"], Z[1]["T"], Z[1]["R"])]
    frames=int(FPS*seconds)
    for f in range(frames):
        t=f/frames; px=frame_fill(BG_DIM)
        for lefts,top,rights in chains:
            for seg in (lefts, rights):
                L=len(seg); up=int(L*min(1.0,t*1.4))
                for idx in seg[:up]: add(px,idx,scale(color,0.7))
            L=len(top); center=L//2; spread=max(1, int((L/2)*t))
            for k in range(center-spread, center+spread+1):
                if 0<=k<L:
                    i=top[k]; fall=1.0-abs(k-center)/max(1,spread)
                    add(px,i,mix(color,WHITE,0.5*fall))
        send_frame(px); time.sleep(1/FPS)

def column_climb(base, accent, seconds=1.1, length=8, glow=0.5):
    frames=int(FPS*seconds)
    for f in range(frames):
        t=f/frames; pos=int(t*(len(LEFT_CHAIN)-1))
        px=frame_fill(BG_DIM)
        for j in range(length):
            for chain,color in ((LEFT_CHAIN,accent),(RIGHT_CHAIN,base)):
                i=pos-j
                if 0<=i<len(chain):
                    idx=chain[i]; k=max(0.0,1.0-j/length)
                    add(px,idx,scale(color,glow+k))
        send_frame(px); time.sleep(1/FPS)

def ladder_loop(color, seconds=1.6, length=12, glow=0.45):
    path = list(chain.from_iterable([LEFT_CHAIN, TOPS_CHAIN,
                                     list(reversed(RIGHT_CHAIN)),
                                     list(reversed(TOPS_CHAIN))]))
    frames=int(FPS*seconds)
    for f in range(frames):
        t=f/frames; pos=int(t*len(path)); px=frame_fill(BG_DIM)
        for j in range(length):
            i=pos-j
            if 0<=i<len(path):
                idx=path[i]; k=max(0.0,1.0-j/length)
                add(px,idx,scale(color,glow+k))
        send_frame(px); time.sleep(1/FPS)

def shard_rain(color, seconds=1.2, density=0.09):
    frames=int(FPS*seconds)
    active=[]; tops=TOPS_CHAIN
    sides=LEFT_CHAIN+RIGHT_CHAIN
    for f in range(frames):
        if random.random()<density:
            spawn=random.choice(tops); target=random.choice(sides)
            active.append({"pos":spawn,"target":target,"life":random.randint(12,20)})
        px=frame_fill(BG_DIM)
        for s in active[:]:
            life=s["life"]; 
            if life<=0: active.remove(s); continue
            pi=PATH.index(s["pos"]); ti=PATH.index(s["target"])
            step=2 if (ti-pi)%len(PATH)<(pi-ti)%len(PATH) else -2
            s["pos"]=PATH[(pi+step)%len(PATH)]; s["life"]-=1
            add(px,s["pos"],mix(color,WHITE,0.4))
        send_frame(px); time.sleep(1/FPS)

def dual_comet(color, accent, seconds=4.6, length=14, glow=0.55):
    frames=int(FPS*seconds); total=len(PATH)
    for f in range(frames):
        t=f/frames; h1=int(t*total)%total; h2=(total-h1)%total
        px=frame_fill(BG_DIM)
        def draw(head,col):
            for j in range(length):
                idx=(head-j)%total; p=PATH[idx]; k=max(0.0,1.0-j/length)
                add(px,p,scale(col,k))
                if glow>0 and j<length-1:
                    for side in(-1,+1):
                        q=PATH[(idx+side)%total]
                        add(px,q,scale(col,glow*k*0.5))
        draw(h1,accent); draw(h2,color)
        send_frame(px); time.sleep(1/FPS)

def prism_tops(color, seconds=1.0):
    chain=TOPS_CHAIN; frames=int(FPS*seconds); trail=12
    for f in range(frames):
        t=f/frames; pos=int(t*(len(chain)+trail)); px=frame_fill(BG_DIM)
        for k in range(trail):
            i=pos-k
            if 0<=i<len(chain):
                idx=chain[i]; w=max(0.0,1.0-k/trail)
                add(px,idx,mix(color,WHITE,0.75*w))
        send_frame(px); time.sleep(1/FPS)

def lightning_bridge(base, accent=WHITE, seconds=1.2, density=0.18):
    path=TOPS_CHAIN; L=len(path); frames=int(FPS*seconds)
    for f in range(frames):
        t=f/frames; px=frame_fill(BG_DIM)
        head=int(t*(L-1)); width=12
        for i in range(L):
            d=abs(i-head)
            if d<=width:
                jitter=0.6+0.4*random.random()
                k=max(0.0,1.0-d/(width+1))
                col=mix(accent,base,0.3+0.7*(1.0-k))
                add(px,path[i],scale(col,k*jitter))
        for ends in (LEFT_CHAIN[:3]+LEFT_CHAIN[-3:], RIGHT_CHAIN[:3]+RIGHT_CHAIN[-3:]):
            for idx in ends:
                if random.random()<density:
                    add(px,idx,mix(WHITE,base,0.5))
        send_frame(px); time.sleep(1/FPS)

def global_sparkstorm(base, accent=WHITE, seconds=1.9, density=0.65, intensity_mult=2.6):
    frames=int(FPS*seconds)
    for f in range(frames):
        px=frame_fill(BG_DIM)
        for i in range(N):
            if random.random()<density:
                w = random.uniform(0.7, 1.0)
                col = mix(base, accent, w)
                add(px, i, scale(col, intensity_mult*w))
        if random.random()<0.15:
            boost = random.uniform(0.4,0.7)
            for i in range(N):
                add(px, i, scale(accent, boost))
        send_frame(px); time.sleep(1/FPS)
    flash = frame_fill(mix(base, accent, 0.85))
    send_frame([scale(c, 2.4) for c in flash]); time.sleep(0.06)

def supernova(color, seconds=0.65):
    frames=int(FPS*seconds)
    for f in range(frames):
        t=f/frames; px=frame_fill(mix(WHITE,color,t))
        upto=int(len(PATH)*t)
        for i in PATH[:upto]:
            add(px,i,scale(color,0.6*(1.0-t)))
        send_frame(px); time.sleep(1/FPS)

def settle(color, seconds=1.0):
    frames=int(FPS*seconds)
    for f in range(frames):
        k=0.85+0.15*math.sin(f*2*math.pi/(FPS*0.9))
        send_frame(frame_fill(scale(color,k))); time.sleep(1/FPS)

# ===== SECUENCIA =====
def ranger_show(name):
    base, accent = RANGERS[name]
    vortex((0.0,0.20), base, accent, seconds=1.1, spin=2.3)
    volumetric_beam(base, seconds=0.9)
    column_climb(base, accent, seconds=1.1)
    ladder_loop(base, seconds=3.6)
    shard_rain(base, seconds=2.0, density=0.10)
    dual_comet(base, accent, seconds=4.6)
    prism_tops(base, seconds=1.0)
    lightning_bridge(base, accent=accent, seconds=1.2)
    global_sparkstorm(base, accent=accent, seconds=1.9, density=0.65, intensity_mult=2.6)
    supernova(base, seconds=0.65)
    settle(base, seconds=1.0)

# ===== MAIN =====
if __name__ == "__main__":
    random.seed()
    try:
        send_frame(frame_fill(BG_DIM)); time.sleep(0.25)
        for r in ORDER:
            ranger_show(r)
    finally:
        pass
