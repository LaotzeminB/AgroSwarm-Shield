import sys
import os
import json
import requests

from app.security import generate_mesh_signature, encrypt_mesh_payload

# En Windows, la consola clásica (cmd.exe) no siempre entiende ni el UTF-8
# (emojis, acentos) ni los códigos de color ANSI. Estas dos líneas arreglan
# ambas cosas sin afectar Mac/Linux, donde ya funcionan de por sí.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    os.system("")

API_URL = "http://127.0.0.1:8000"

# --- Colores y estilos de consola ---
GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

ANCHO = 70
resultados = []  # (nombre_de_la_prueba, paso: bool)


def print_banner(titulo):
    print(f"\n{BOLD}{YELLOW}┌{'─' * (ANCHO - 2)}┐{RESET}")
    print(f"{BOLD}{YELLOW}│{titulo.center(ANCHO - 2)}│{RESET}")
    print(f"{BOLD}{YELLOW}└{'─' * (ANCHO - 2)}┘{RESET}\n")


def print_step(numero, texto, color=GREEN):
    print(f"{color}{BOLD}[{numero}]{RESET} {color}{texto}{RESET}")


def print_pretty(titulo, res):
    print(f"{DIM}{'-' * ANCHO}{RESET}")
    print(f"{CYAN}{BOLD}» {titulo}{RESET}  {DIM}(HTTP {res.status_code}){RESET}")
    try:
        print(json.dumps(res.json(), indent=4, ensure_ascii=False))
    except Exception:
        print(f"{RED}Respuesta sin JSON legible: {res.text}{RESET}")
    print(f"{DIM}{'-' * ANCHO}{RESET}\n")


def registrar(nombre, paso):
    resultados.append((nombre, paso))


def test_flow():
    print_banner("🛡️  FLUJO NORMAL DE CIBERSEGURIDAD (DÍAS 1-3)")

    # 1. Autenticación de Rancho
    print_step(1, "Iniciando sesión con JWT...")
    res_login = requests.post(f"{API_URL}/api/v1/auth/login", json={
        "username": "rancho_utma",
        "password": "agrotech2026"
    })
    print_pretty("Respuesta de Autenticación", res_login)
    registrar("Login JWT", res_login.status_code == 200)

    if res_login.status_code != 200:
        print(f"{RED}Error en login, se detiene la prueba.{RESET}")
        return

    token = res_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Despliegue de Enjambre (Firmado HMAC + Cifrado)
    print_step(2, "Enviando orden de despliegue de enjambre cifrado...")
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
    registrar("Despliegue de enjambre", res_mission.status_code == 200)

    # 3. Disparo del KILL-SWITCH (Paro de Emergencia)
    print_step(3, "¡ALERTA! Activando botón de emergencia (KILL-SWITCH)...", color=RED)
    res_kill = requests.post(
        f"{API_URL}/api/v1/security/kill-switch",
        headers=headers,
        json={"reason": "Simulación de Intento de Jamming Externo"}
    )
    print_pretty("Respuesta Kill-Switch (Opcode 0xFF)", res_kill)
    registrar("Kill-switch de emergencia", res_kill.status_code == 200)


def test_mesh_intrusion_flow():
    print_banner("🕵️  VALIDADOR ANTI-INTRUSIÓN DEL ENJAMBRE (DÍAS 7-8)")

    comando = "DEPLOY:TERRENO-AGUASCALIENTES-NORTE:5"

    # 1. Orden LEGÍTIMA: simula un nodo ESP32 real, que sí conoce las claves
    # compartidas (Fernet + HMAC) y por lo tanto puede cifrar y firmar
    # correctamente el comando.
    print_step(1, "Nodo ESP32 legítimo enviando orden cifrada y firmada...")
    payload_legitimo = encrypt_mesh_payload(comando)
    firma_legitima = generate_mesh_signature(comando)
    res_legit = requests.post(f"{API_URL}/api/v1/mesh/order", json={
        "encrypted_payload": payload_legitimo,
        "signature": firma_legitima
    })
    print_pretty("Orden Legítima", res_legit)
    registrar("Orden legítima aceptada", res_legit.status_code == 200)

    # 2. HACKER intento #1: no conoce ni la clave Fernet ni el secreto HMAC,
    # así que solo puede inventar un paquete al azar.
    print_step(2, "🕵️ HACKER intentando inyectar un paquete inventado (sin claves)...", color=RED)
    res_hacker_1 = requests.post(f"{API_URL}/api/v1/mesh/order", json={
        "encrypted_payload": "esto_no_es_un_paquete_cifrado_real",
        "signature": "firma_inventada_por_el_hacker"
    })
    print_pretty("Intento de Intrusión #1 (paquete falso)", res_hacker_1)
    registrar("Paquete falso rechazado", res_hacker_1.status_code == 401)

    # 3. HACKER intento #2: intercepta el paquete cifrado legítimo (ej. por un
    # sniffer en la red) pero no conoce el secreto HMAC, así que no puede
    # firmar el comando real y usa una firma falsa.
    print_step(3, "🕵️ HACKER interceptó el paquete real pero falsifica la firma...", color=RED)
    res_hacker_2 = requests.post(f"{API_URL}/api/v1/mesh/order", json={
        "encrypted_payload": payload_legitimo,
        "signature": "0000000000firma_falsa0000000000"
    })
    print_pretty("Intento de Intrusión #2 (firma falsificada)", res_hacker_2)
    registrar("Firma falsificada rechazada", res_hacker_2.status_code == 401)


def print_resumen():
    print_banner("📋  RESUMEN DE LA PRUEBA")
    for nombre, paso in resultados:
        marca = f"{GREEN}✔ OK    {RESET}" if paso else f"{RED}✘ FALLÓ {RESET}"
        print(f"  {marca} {nombre}")

    total = len(resultados)
    exitosos = sum(1 for _, paso in resultados if paso)
    print()
    if exitosos == total:
        print(f"{GREEN}{BOLD}✅ TODO CORRECTO: {exitosos}/{total} pruebas pasaron.{RESET}\n")
    else:
        print(f"{RED}{BOLD}⚠️  REVISAR: solo {exitosos}/{total} pruebas pasaron.{RESET}\n")


if __name__ == "__main__":
    test_flow()
    test_mesh_intrusion_flow()
    print_resumen()
