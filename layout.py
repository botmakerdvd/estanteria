# layout.py
# Definición unificada para estructura de 132 LEDs (4 Zonas)
# CORREGIDO tras test visual: Z1_T y Z1_L invertidos.

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

N = 132  # Total LEDs

def calculate_unified_layout():
    """
    Genera el mapeo completo de 132 LEDs en una sola pasada.
    Configuración: (Nombre, Cantidad, ¿Invertido?)
    """
    SEGMENTS_CONFIG = [
        # --- ZONA 4 (Abajo: 0-29) ---
        ("B_L", 6,  False), # 0-5
        ("B_T", 18, False), # 6-23
        ("B_R", 6,  True),  # 24-29 (Inv)

        # --- ZONA 3 (Medio: 30-59) ---
        ("M_R", 6,  False), # 30-35
        ("M_T", 18, True),  # 36-53 (Inv)
        ("M_L", 6,  True),  # 54-59 (Inv)

        # --- ZONA 2 (Arriba Viejo: 60-95) ---
        ("T_L", 9,  False), # 60-68
        ("T_T", 18, False), # 69-86
        ("T_R", 9,  True),  # 87-95 (Inv)

        # --- ZONA 1 (Estante Nuevo: 96-131) ---
        # AJUSTES TRAS DIAGNÓSTICO:
        ("Z1_R", 9,  False), # 96-104 (Columna Derecha: Correcta)
        ("Z1_T", 18, True),  # 105-122 (Techo: INVERTIDO para ir de Izq->Der)
        ("Z1_L", 9,  True),  # 123-131 (Columna Izquierda: INVERTIDA para ir de Abajo->Arriba)
    ]

    index_map = {}
    current_id = 0
    full_path = []

    for name, length, is_reversed in SEGMENTS_CONFIG:
        # Generar rango de IDs para este segmento
        ids = list(range(current_id, current_id + length))
        
        # Aplicar inversión lógica si el cableado lo requiere
        if is_reversed:
            ids.reverse()
            
        index_map[name] = ids
        full_path += ids # Camino lógico completo para efectos de barrido
        current_id += length

    return index_map, full_path

# --- EJECUCIÓN DEL CÁLCULO ---
INDEX, FULL_PATH = calculate_unified_layout()

# --- DEFINICIÓN DE ZONAS ---
# Construimos las zonas simplemente sumando las listas del INDEX ya calculado
ZONE4 = INDEX["B_L"] + INDEX["B_T"] + INDEX["B_R"]  # Abajo
ZONE3 = INDEX["M_L"] + INDEX["M_T"] + INDEX["M_R"]  # Medio
ZONE2 = INDEX["T_L"] + INDEX["T_T"] + INDEX["T_R"]  # Arriba
ZONE1 = INDEX["Z1_R"] + INDEX["Z1_T"] + INDEX["Z1_L"] # Super-Arriba (Nuevo)

# Sets para búsqueda rápida
ZONE1_SET, ZONE2_SET, ZONE3_SET, ZONE4_SET = set(ZONE1), set(ZONE2), set(ZONE3), set(ZONE4)

# Alias para compatibilidad con lógica de efectos (Top/Middle/Bottom)
TOP_ZONE, MIDDLE_ZONE, BOTTOM_ZONE = ZONE2, ZONE3, ZONE4

# --- MAPA DE PROPIEDADES DE ZONA (Reglas) ---
ZONE_PROPERTIES_MAP = {
    "ZONE1": {"set": ZONE1_SET, "white_allowed": True},  # Única zona con blanco permitido
    "ZONE2": {"set": ZONE2_SET, "white_allowed": False},
    "ZONE3": {"set": ZONE3_SET, "white_allowed": False},
    "ZONE4": {"set": ZONE4_SET, "white_allowed": False},
}

def white_allowed(i: int) -> bool:
    """Consulta si el LED 'i' permite color blanco puro."""
    for props in ZONE_PROPERTIES_MAP.values():
        if i in props["set"]:
            return props["white_allowed"]
    return False