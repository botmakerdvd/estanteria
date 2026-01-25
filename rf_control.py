# rf_control.py
# Cliente RF para Torre Reloj.
# Se conecta al rf_server.py local para evitar problemas de timing/CPU en el proceso principal.

import socket
import time

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 65432

class RFManager:
    def __init__(self):
        # En cliente simple UDP/TCP sin persistencia no necesitamos mucha inicialización,
        # pero verificamos si el servidor está "alcanzable" conceptualmente o simplemente lanzamos errores.
        # Para evitar bloquear el show por un fallo de red local, seremos silenciosos en errores de conexión
        # pero loguearemos.
        pass

    def send(self, name_or_code):
        """
        Envía un comando al servidor RF.
        name_or_code: Nombre del comando (str) o código raw (int).
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2) # Timeout muy corto para no bloquear videoplayback
                s.connect((SERVER_HOST, SERVER_PORT))
                msg = str(name_or_code)
                s.sendall(msg.encode('utf-8'))
        except ConnectionRefusedError:
            print(f"[RF-Client] ERROR: No se pudo conectar al RF Server en {SERVER_HOST}:{SERVER_PORT}. ¿Está corriendo?")
        except Exception as e:
            print(f"[RF-Client] ERROR enviando comando '{name_or_code}': {e}")

    def cleanup(self):
        # Nada que limpiar en el cliente stateless
        pass

    def reset_sequence(self):
        """
        Envía la secuencia de reset: ON -> ON -> FUNCT8
        (Para asegurar que el coche vuelve a estado base)
        """
        try:
            # print("RF Manager: Sending Reset Sequence...")
            #self.send("onoff"); time.sleep(1.0)
            #self.send("onoff"); time.sleep(1.0)
            self.send("funct8")
        except: pass