# rf_control.py
# VERSIÓN FINAL AFINADA: Multiprocessing + Repeat Moderado
# Bajamos las repeticiones para evitar el efecto "rebote" (enciende-apaga),
# pero mantenemos el proceso aislado para que la señal sea limpia.

import time
import os
import multiprocessing
import queue

# ========= CONFIGURACIÓN RF =========
TX_PULSELENGTH = 396
TX_PROTOCOL    = 1
TX_GPIO        = 17
TX_LENGTH      = 24

# AJUSTES DE ROBUSTEZ (AFINADO)

# TX_REPEAT_PACKET: Bajamos de 15 a 6.
# Con el mando manual usabas 4 y iba bien.
# Con 15 era tan largo que el ruido lo partía en dos y el receptor veía doble pulsación.
# 6 u 8 es el punto dulce para receptores 'toggle'.
TX_REPEAT_PACKET = 10   

# ENVIOS_POR_COMANDO: Mantenemos en 1.
# Solo enviamos la orden una vez.
ENVIOS_POR_COMANDO = 1 

# GAPs (Seguridad)
GAP_ENTRE_REPETICIONES = 0.05 
TX_GAP_FINAL = 0.15

# ========= CÓDIGOS DEFINIDOS =========
CODES = {
    "front":        1744397,
    "interior":     1744398,
    "rear":         1744399,
    "blue_front":   1744400,
    "blue_rear":    1744401,
    "wheels":       1744402,
    "flux":         1744403,
}

def rf_worker_process(cmd_queue):
    # Intentamos máxima prioridad para evitar jitter
    try:
        os.nice(-20)
        print("[RF-Worker] Prioridad -20 establecida.")
    except:
        pass

    from rpi_rf import RFDevice
    rfdevice = RFDevice(TX_GPIO)
    rfdevice.enable_tx()
    # Aplicamos el repeat moderado
    rfdevice.tx_repeat = TX_REPEAT_PACKET
    
    print(f"[RF-Worker] Listo. Repeat Packet: {TX_REPEAT_PACKET}")

    while True:
        try:
            # Esperamos orden del script principal
            code = cmd_queue.get()
            if code is None: break

            # Solo enviamos 1 vez, pero con la longitud justa
            for i in range(ENVIOS_POR_COMANDO):
                rfdevice.tx_code(code, TX_PROTOCOL, TX_PULSELENGTH, TX_LENGTH)
                if ENVIOS_POR_COMANDO > 1:
                    time.sleep(GAP_ENTRE_REPETICIONES)

            # Pausa final para limpiar canal
            time.sleep(TX_GAP_FINAL)
            
        except Exception as e:
            print(f"[RF-Worker] Error: {e}")

    rfdevice.cleanup()
    print("[RF-Worker] Cerrando.")

class RFManager:
    def __init__(self):
        self.queue = multiprocessing.Queue()
        self.process = multiprocessing.Process(target=rf_worker_process, args=(self.queue,))
        self.process.daemon = True
        self.process.start()

    def send(self, name_or_code):
        code_to_send = None
        if isinstance(name_or_code, str):
            code_to_send = CODES.get(name_or_code)
        elif isinstance(name_or_code, int):
            code_to_send = name_or_code

        if code_to_send:
            self.queue.put(code_to_send)
        else:
            print(f"[RF] Código desconocido: {name_or_code}")

    def cleanup(self):
        self.queue.put(None)
        self.process.join(timeout=1)
        if self.process.is_alive(): self.process.terminate()