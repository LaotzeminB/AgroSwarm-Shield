# AgroSwarm Shield — Backend & Ciberseguridad

Backend de la red de micro-drones agrícolas autónomos y biodegradables
**AgroSwarm Shield**, encargado de la autenticación, el cifrado de las
órdenes hacia el enjambre y la protección contra intentos de intrusión.

> Equipo BITBEE — Esta rama contiene el trabajo de **Backend,
> Ciberseguridad & Protocolos**.

## ¿Qué hace este backend?

Protege la comunicación **Servidor ↔ App ↔ Dron** con 3 capas de
seguridad:

1. **JWT** — autentica a la app del rancho antes de dejarla operar el enjambre.
2. **Cifrado Fernet** — para que nadie pueda leer las órdenes en tránsito.
3. **Firma HMAC** — para que el servidor rechace cualquier orden que no
   venga realmente de un nodo autorizado (dron/ESP32).

Además, transmite telemetría y alertas en tiempo real por WebSocket, y
lleva una bitácora de cada intento de intrusión bloqueado.

## Stack

- **FastAPI** (Python) — servidor y API REST + WebSocket
- **python-jose** — tokens JWT
- **cryptography (Fernet)** — cifrado simétrico de las órdenes al enjambre
- **pwdlib** — hash seguro de contraseñas
- **python-dotenv** — carga de claves desde `.env`

## Cómo correrlo

**1. Crear el entorno virtual e instalar dependencias:**
```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**2. Crear un archivo `.env`** en la raíz del proyecto con estas 3 claves
(genera valores propios, no compartas las tuyas):
```
JWT_SECRET_KEY=<una cadena larga y aleatoria>
MESH_HMAC_SECRET=<otra cadena larga y aleatoria>
FERNET_KEY=<una clave Fernet válida, generada con Fernet.generate_key()>
```

**3. Arrancar el servidor:**
```
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

**4. Ver la documentación interactiva de la API:**
Abre `http://127.0.0.1:8000/docs` en el navegador.

## Endpoints principales

| Método | Ruta | Qué hace |
|---|---|---|
| POST | `/api/v1/auth/login` | Login del rancho, entrega el token JWT |
| POST | `/api/v1/mission/start` | Despliega el enjambre sobre un terreno |
| POST | `/api/v1/security/kill-switch` | Botón de emergencia: corta corriente a los drones |
| POST | `/api/v1/mesh/order` | Recibe una orden del enjambre, valida cifrado + firma, rechaza intrusos |
| GET | `/api/v1/security/intrusion-log` | Bitácora de intentos de intrusión bloqueados |
| WS | `/api/v1/ws/telemetry` | Canal en tiempo real: telemetría de drones + alertas |

## Pruebas incluidas

- **`hacker_simulator.py`** — corre el flujo normal (login, misión,
  kill-switch) y luego simula un ataque: una orden legítima y dos
  intentos de "hacker" (paquete inventado y firma falsificada),
  mostrando un resumen de qué se bloqueó.
  ```
  .venv\Scripts\python.exe hacker_simulator.py
  ```

- **`esp32_simulator.py`** — simula un nodo ESP32 en Python (sin
  necesitar el hardware físico): se conecta al canal de telemetría,
  verifica la firma del kill-switch y "corta motores", midiendo el
  tiempo de reacción. Útil como respaldo de demo si el hardware real no
  está disponible.
  ```
  .venv\Scripts\python.exe esp32_simulator.py
  ```

- **`esp32_firmware/kill_switch_node/`** — firmware real en C++/Arduino
  para subir a un ESP32 físico, con la misma lógica de verificación.

## Estructura del proyecto

```
├── app/
│   ├── main.py        # Endpoints FastAPI (REST + WebSocket)
│   └── security.py     # JWT, hash de passwords, HMAC, cifrado/descifrado Fernet
├── esp32_firmware/
│   └── kill_switch_node/kill_switch_node.ino
├── esp32_simulator.py
├── hacker_simulator.py
└── requirements.txt
```

## Organización de ramas

Cada integrante trabaja en su propia rama:

- `laotzemin-backend-seguridad` — Backend, ciberseguridad y protocolos (esta rama)
- `gus-frontend-movil` — App móvil, UI/UX, mapas
- `richard-backend-datos` — Base de datos y simulador de telemetría
- `aleman-hardware-dron` — Prototipo físico y firmware del dron

`main` se mantiene sin contenido hasta que el equipo decida juntar el
trabajo final de todas las ramas.
