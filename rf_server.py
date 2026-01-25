#!/usr/bin/env python3
# rf_server.py
# VERSIÓN LOW-LATENCY (Post-Optimización de Video)
# - CPU relajada gracias a hardware decoding.
# - Eliminamos subprocess para quitar latencia.
# - Ejecución directa vía rpi_rf en hilo dedicado.

import socket
import time
import sys
import threading
import queue
import os
from rpi_rf import RFDevice

# ========= CONFIGURACIÓN RF (Ajustes de Usuario) =========
TX_PULSELENGTH = 396
TX_PROTOCOL    = 1
TX_GPIO        = 17
TX_LENGTH      = 24
TX_REPEAT      = 6    # Usuario ajustó a 6
GAP_ENTRE_CMD  = 0.15  # Usuario ajustó a 0.1

# ========= CONFIGURACIÓN SOCKET =========
HOST = "127.0.0.1"
PORT = 65432

# ========= CÓDIGOS =========
CODES = {
    "front":        1744397,
    "interior":     1744398,
    "rear":         1744399,
    "blue_front":   1744400,
    "blue_rear":    1744401,
    "wheels":       1744402,
    "flux":         1744403,
    "onoff":        1744385,
    "funct8":       1744404,
}

# Cola de comandos
cmd_queue = queue.Queue()

def setup_priority():
    try:
        # Mantenemos alta prioridad por si acaso, no hace daño
        os.nice(-20)
        print("[RF-Server] Priority: OK (-20)")
    except:
        pass

def rf_worker_loop():
    setup_priority()
    print("[RF-Worker] Iniciando hilo Direct-RF (Low Latency)...")
    
    try:
        while True:
            item = cmd_queue.get()
            if item is None: break
            
            cmd_name, code = item
            print(f"[RF-Worker] >>> Enviando: {cmd_name} ({code})")
            
            # Instanciamos y enviamos DIRECTAMENTE (Cero latencia de proceso)
            device = None
            try:
                device = RFDevice(TX_GPIO)
                device.enable_tx()
                device.tx_repeat = TX_REPEAT
                device.tx_code(code, TX_PROTOCOL, TX_PULSELENGTH, TX_LENGTH)
            except Exception as e:
                print(f"[RF-Worker] ERROR TX: {e}")
            finally:
                if device: 
                    device.cleanup()
            
            # Pequeño gap para no atropellar al receptor
            time.sleep(GAP_ENTRE_CMD)
            cmd_queue.task_done()
            
    except Exception as e:
        print(f"[RF-Worker] Crash: {e}")
    finally:
        print("[RF-Worker] Stop.")

def handle_client(conn):
    try:
        data = conn.recv(1024)
        if data:
            cmd = data.decode('utf-8').strip()
            code = CODES.get(cmd)
            if code:
                cmd_queue.put((cmd, code))
            elif cmd.isdigit():
                cmd_queue.put(("RAW", int(cmd)))
            else:
                print(f"[RF-Server] Ignorado: {cmd}")
    except:
        pass
    finally:
        conn.close()

def main():
    print("[RF-Server] Iniciando Modo Rápido (Direct In-Process)...")
    print(f"            Config: Repeat={TX_REPEAT}, Gap={GAP_ENTRE_CMD}")
    
    t_worker = threading.Thread(target=rf_worker_loop, daemon=True)
    t_worker.start()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"[RF-Server] Escuchando en {HOST}:{PORT}")
        
        try:
            while True:
                conn, addr = s.accept()
                handle_client(conn)
        except KeyboardInterrupt:
            print("\n[RF-Server] Bye.")
            cmd_queue.put(None)
            t_worker.join(timeout=1)

if __name__ == "__main__":
    main()
