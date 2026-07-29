import requests
import json

API_URL = "http://127.0.0.1:8000"

# Colores de consola
GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RESET = "\033[0m"

def print_pretty(title, res):
    print(f"\n{CYAN}=== {title} (Status: {res.status_code}) ==={RESET}")
    try:
        print(json.dumps(res.json(), indent=4, ensure_ascii=False))
    except Exception:
        print(f"{RED}Respuesta sin JSON legible: {res.text}{RESET}")

def test_flow():
    print(f"\n{YELLOW}🛡️ AGROSWARM SHIELD - PRUEBA DE FLUJO DE CIBERSEGURIDAD (DÍAS 1-3){RESET}\n")

    # 1. Autenticación de Rancho
    print(f"{GREEN}[1] Intentando Inicio de Sesión con JWT...{RESET}")
    res_login = requests.post(f"{API_URL}/api/v1/auth/login", json={
        "username": "rancho_utma",
        "password": "agrotech2026"
    })
    
    if res_login.status_code != 200:
        print(f"{RED}Error en login ({res_login.status_code}): {res_login.text}{RESET}")
        return
        
    token = res_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print_pretty("Respuesta de Autenticación", res_login)

    # 2. Despliegue de Enjambre (Firmado HMAC)
    print(f"\n{GREEN}[2] Enviando Orden de Despliegue de Enjambre Cifrado...{RESET}")
    res_mission = requests.post(
        f"{API_URL}/api/v1/mission/start",
        headers=headers,
        json={
            "terreno_id": "TERRENO-AGUASCALIENTES-NORTE",
            "polygon_coordinates": [[21.8823, -102.2826], [21.8830, -102.2810]],
            "num_drones": 5
        }
    )
    print_pretty("Respuesta Despliegue Enjambre", res_mission)

    # 3. Disparo del KILL-SWITCH (Paro de Emergencia)
    print(f"\n{RED}[3] ¡ALERTA! Activando Botón de Emergencia (KILL-SWITCH)...{RESET}")
    res_kill = requests.post(
        f"{API_URL}/api/v1/security/kill-switch",
        headers=headers,  # <--- Pasamos las cabeceras con el JWT
        json={"reason": "Simulación de Intento de Jamming Externo"}
    )
    print_pretty("Respuesta Kill-Switch (Opcode 0xFF)", res_kill)

if __name__ == "__main__":
    test_flow()