import sys
import asyncio
import json
import time
import websockets

from app.security import verify_mesh_signature

# En Windows, la consola clásica no siempre entiende bien los acentos.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SERVER_WS_URL = "ws://127.0.0.1:8000/api/v1/ws/telemetry"

COMANDO_KILL_SWITCH = "KILL_SWITCH_ALL_MOTORS_OFF"

motores_encendidos = True


async def escuchar_servidor():
    global motores_encendidos
    print(f"[ESP32-SIM] Conectando a {SERVER_WS_URL} ...")
    async with websockets.connect(SERVER_WS_URL) as ws:
        print("[ESP32-SIM] Conectado. Simulando nodo ESP32 en espera de ordenes.\n")

        async for mensaje_json in ws:
            inicio = time.perf_counter()
            try:
                data = json.loads(mensaje_json)
            except json.JSONDecodeError:
                print("[ESP32-SIM] Mensaje no es JSON valido, se ignora.")
                continue

            evento = data.get("event")

            if evento == "KILL_SWITCH_ACTIVADO":
                firma_recibida = data.get("signature_hmac", "")

                if verify_mesh_signature(COMANDO_KILL_SWITCH, firma_recibida):
                    motores_encendidos = False
                    tiempo_ms = (time.perf_counter() - inicio) * 1000
                    print(f"[ESP32-SIM] 🔴 MOTORES CORTADOS. Tiempo de reaccion: {tiempo_ms:.2f} ms")
                else:
                    print("[ESP32-SIM] 🚨 ALERTA: Kill-switch con firma INVALIDA. Se ignora (posible intrusion).")

            elif evento == "INTENTO_INTRUSION":
                print(f"[ESP32-SIM] ⚠️  El servidor reporta un intento de intrusion: {data.get('detalle')}")

            elif evento == "TELEMETRIA":
                pass  # el simulador solo reacciona al kill-switch, no imprime cada telemetria


if __name__ == "__main__":
    print("=" * 60)
    print(" AGROSWARM SHIELD - Simulador de nodo ESP32 (sin hardware)")
    print("=" * 60)
    asyncio.run(escuchar_servidor())
