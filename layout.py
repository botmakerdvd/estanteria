# layout.py
# Definición unificada para estructura de 153 LEDs (4 Zonas + Fuego + Estante 0)
# Zonas: Z4 -> Z3 -> FUEGO -> Z2 -> Z1 -> Z0

from typing import Dict, List

# ========= CONSTANTES DE COLOR =========
WHITE          = (255, 255, 255)
ELECTRIC_BLUE  = (150, 200, 255)
DEEP_BLUE      = (30, 90, 200)
ORANGE_INTENSE = (255, 80, 0)
AMBER_SOFT     = (255, 140, 40)
RED_SIREN      = (255, 0, 20)
BLUE_SIREN     = (0, 80, 255)
GREEN_CIRCUITS = (60, 255, 80)
YELLOW_WARM    = (255, 200, 40)

# Total LEDs: 143 (antiguos) + 10 (fuego) = 153
N = 153  

def calculate_unified_layout():
    """
    Genera el mapeo completo.
    Orden físico: Z4 -> Z3 -> FUEGO -> Z2 -> Z1 -> Z0
    """
    SEGMENTS_CONFIG = [
        # --- ZONA 4 (Abajo: 0-29) ---
        ("B_L", 6,  False),
        ("B_T", 18, False),
        ("B_R", 6,  True), 

        # --- ZONA 3 (Medio: 30-59) ---
        ("M_R", 6,  False),
        ("M_T", 18, True),
        ("M_L", 6,  True), 

        # --- ZONA FUEGO (Nueva: 10 LEDs entre Z3 y Z2) ---
        # Asumo que no está invertida, pero si lo está cambia False por True
        ("Z_FIRE", 10, False),

        # --- ZONA 2 (Arriba Viejo: 70-105) ---
        ("T_L", 9,  False),
        ("T_T", 18, False),
        ("T_R", 9,  True), 

        # --- ZONA 1 (Estante Zords: 106-141) ---
        ("Z1_R", 9,  False), 
        ("Z1_T", 18, True),  
        ("Z1_L", 9,  True),  

        # --- ZONA 0 (Villanos: 142-152) ---
        ("Z0_Special", 11, False), 
    ]

    index_map = {}
    current_id = 0
    full_path = []

    for name, length, is_reversed in SEGMENTS_CONFIG:
        ids = list(range(current_id, current_id + length))
        if is_reversed:
            ids.reverse()
        index_map[name] = ids
        full_path += ids
        current_id += length

    return index_map, full_path

# --- EJECUCIÓN ---
INDEX, FULL_PATH = calculate_unified_layout()

# --- DEFINICIÓN DE ZONAS ---
ZONE4 = INDEX["B_L"] + INDEX["B_T"] + INDEX["B_R"]
ZONE3 = INDEX["M_L"] + INDEX["M_T"] + INDEX["M_R"]
ZONE_FIRE = INDEX["Z_FIRE"] # Nueva zona
ZONE2 = INDEX["T_L"] + INDEX["T_T"] + INDEX["T_R"]
ZONE1 = INDEX["Z1_R"] + INDEX["Z1_T"] + INDEX["Z1_L"]
ZONE0 = INDEX["Z0_Special"]

ZONE1_SET, ZONE2_SET, ZONE3_SET, ZONE4_SET, ZONE0_SET, ZONE_FIRE_SET = \
    set(ZONE1), set(ZONE2), set(ZONE3), set(ZONE4), set(ZONE0), set(ZONE_FIRE)

# --- MAPA DE PROPIEDADES DE ZONA ---
ZONE_PROPERTIES_MAP = {
    "ZONE0": {"set": ZONE0_SET, "white_allowed": True},
    "ZONE1": {"set": ZONE1_SET, "white_allowed": True},
    "ZONE2": {"set": ZONE2_SET, "white_allowed": False},
    "ZONE3": {"set": ZONE3_SET, "white_allowed": False},
    "ZONE4": {"set": ZONE4_SET, "white_allowed": False},
    "ZONE_FIRE": {"set": ZONE_FIRE_SET, "white_allowed": True}, # Fuego permite blanco/amarillo intenso
}

def white_allowed(i: int) -> bool:
    for props in ZONE_PROPERTIES_MAP.values():
        if i in props["set"]:
            return props["white_allowed"]
    return False