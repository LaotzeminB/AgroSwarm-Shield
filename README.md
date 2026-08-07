# 🐝 AgroSwarm Shield

**La primera red de micro-drones agrícolas autónomos y biodegradables
para la protección e inmunización biológica de cultivos, gestionada
desde una app segura.**

Un enjambre de micro-drones eléctricos (hechos de micelio, biodegradables
en 15 días) patrulla los cultivos a nivel de hoja para detectar plagas
antes de que sean visibles a simple vista, y las trata de forma
biológica — sin necesidad de un dron gigante ni químicos pesados. Todo
se gestiona desde una app móvil con cifrado de extremo a extremo.

Proyecto desarrollado para hackathon por el equipo **BITBEE**.

## Equipo BITBEE

| Integrante | Área |
|---|---|
| Sánchez Flores Laotzemin Beatriz (líder) | Backend, ciberseguridad y protocolos |
| Larios Torres Luis Gustavo | Frontend móvil, UI/UX y mapas |
| Garduño Noguez Jorge Ricardo | Base de datos y simulador de telemetría |
| Cruz Alemán Juan Manuel | Prototipo físico, hardware y firmware del dron |

## Servidor en vivo

El backend está desplegado en la nube (dirección fija, sin depender de
ninguna laptop encendida):

```
https://agroswarm-shield.onrender.com/docs
```

La primera petición del día puede tardar unos 30-50 segundos (el plan
gratuito de Render "duerme" el servidor tras 15 minutos sin uso); las
siguientes responden en menos de un segundo.

## Arquitectura

```
 App móvil (Flutter)  <──HTTPS + WebSocket──>  Backend (FastAPI)  <──>  MongoDB Atlas
        │                                            │
        │                                            └──> Mesh cifrada (Fernet + HMAC) ──> Nodos ESP32 (drones)
        └── Mapa satelital, despliegue de misión, telemetría en vivo, kill-switch
```

- **App móvil** (`abeja_app/`) — Flutter. Login, delimitación del
  terreno sobre mapa satelital de Google Maps, cálculo automático de
  drones necesarios, telemetría en vivo por WebSocket y botón de
  emergencia (kill-switch).
- **Backend** (`app/`) — FastAPI (Python). Autenticación JWT, cifrado
  de órdenes, firma digital HMAC, arquitectura de **colmenas
  compartidas** (ver abajo) y canal de telemetría en tiempo real.
- **Base de datos** — MongoDB Atlas (usuarios, bitácora de intrusiones,
  telemetría), compartida con el simulador en C# del equipo
  (`AbejitaSimple/`).
- **Hardware** (`esp32_firmware/`) — firmware real para el nodo ESP32
  que recibe el kill-switch y corta motores, con verificación de firma
  HMAC antes de actuar.

## Ciberseguridad

Tres capas de seguridad protegen la comunicación **Servidor ↔ App ↔ Dron**:

1. **JWT** — autentica a cada rancho antes de dejarlo operar su enjambre.
2. **Cifrado Fernet** — nadie puede leer las órdenes en tránsito.
3. **Firma HMAC** — el servidor rechaza cualquier orden que no venga
   realmente de un nodo autorizado, y registra el intento en una
   bitácora de intrusiones.

### Colmenas compartidas, con privacidad estricta entre clientes

Cuando dos terrenos están cerca (menos de 2 km), comparten la misma
colmena física y se turnan el patrullaje automáticamente — así el
modelo de negocio "Shared" no obliga a cada rancho a comprar su propio
enjambre. **El servidor nunca revela a un cliente los datos de otro**:
cada quien solo recibe por WebSocket la telemetría, coordenadas y
turnos de su propio terreno, aunque estén compartiendo colmena. Esto
está verificado con pruebas automatizadas de múltiples clientes
simultáneos sin fugas de datos.

## Cómo correr el backend en local

**1. Crear el entorno virtual e instalar dependencias:**
```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**2. Crear un archivo `.env`** en la raíz del proyecto (no se sube a git):
```
JWT_SECRET_KEY=<una cadena larga y aleatoria>
MESH_HMAC_SECRET=<otra cadena larga y aleatoria>
FERNET_KEY=<una clave Fernet válida, generada con Fernet.generate_key()>
MONGO_URI=<tu cadena de conexión de MongoDB, local o Atlas>
```

**3. Arrancar el servidor:**
```
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

**4. Documentación interactiva de la API:** `http://127.0.0.1:8000/docs`

**5. Panel web de prueba** (mientras no se corre la app móvil):
`http://127.0.0.1:8000/`

## Cómo correr la app móvil

```
cd abeja_app
flutter pub get
flutter run
```

Por default la app ya apunta al servidor en la nube (arriba), así que
no requiere ninguna configuración. Si quieres apuntarla a tu backend
local durante desarrollo, usa el ícono de engranaje en la pantalla de
login para escribir tu propia dirección.

## Endpoints principales

| Método | Ruta | Qué hace |
|---|---|---|
| POST | `/api/v1/auth/register` | Registra un rancho nuevo |
| POST | `/api/v1/auth/login` | Login del rancho, entrega el token JWT |
| POST | `/api/v1/mission/start` | Despliega el enjambre sobre un terreno (asigna colmena) |
| POST | `/api/v1/security/kill-switch` | Botón de emergencia: corta corriente a los drones |
| POST | `/api/v1/mesh/order` | Recibe una orden del enjambre, valida cifrado + firma, rechaza intrusos |
| GET | `/api/v1/security/intrusion-log` | Bitácora de intentos de intrusión bloqueados |
| WS | `/api/v1/ws/telemetry?token=` | Canal en tiempo real: telemetría de drones + alertas, filtrado por usuario |

## Pruebas incluidas

- **`hacker_simulator.py`** — corre el flujo normal (login, misión,
  kill-switch) y luego simula un ataque: una orden legítima y dos
  intentos de "hacker" (paquete inventado y firma falsificada).
  ```
  .venv\Scripts\python.exe hacker_simulator.py
  ```

- **`esp32_simulator.py`** — simula un nodo ESP32 en Python (sin
  hardware físico): se conecta al canal de telemetría, verifica la
  firma del kill-switch y "corta motores", midiendo el tiempo de
  reacción.
  ```
  .venv\Scripts\python.exe esp32_simulator.py
  ```

- **`esp32_firmware/kill_switch_node/`** — firmware real en C++/Arduino
  para el ESP32 físico, con la misma lógica de verificación.

## Estructura del proyecto

```
├── app/                    # Backend FastAPI
│   ├── main.py              # Endpoints REST + WebSocket, colmenas compartidas
│   ├── security.py          # JWT, hash de passwords, HMAC, cifrado/descifrado Fernet
│   ├── database.py          # Conexión a MongoDB
│   └── static/index.html    # Panel web de prueba
├── abeja_app/               # App móvil (Flutter)
├── AbejitaSimple/           # Simulador de telemetría (C#/.NET), comparte la base de datos
├── esp32_firmware/
│   └── kill_switch_node/kill_switch_node.ino
├── esp32_simulator.py
├── hacker_simulator.py
├── requirements.txt
└── LICENSE
```

## Organización de ramas

- `main` — rama principal, con el trabajo integrado de todo el equipo.
- `laotzemin-backend-seguridad` — Backend, ciberseguridad y protocolos.
- `gus-frontend-movil` — App móvil, UI/UX, mapas.
- `richard-backend-datos` — Base de datos y simulador de telemetría.
- `aleman-hardware-dron` — Prototipo físico y firmware del dron.

## Licencia

Todos los derechos reservados — equipo BITBEE. Ver [`LICENSE`](LICENSE).
