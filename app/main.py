import sys
import asyncio
import random
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Depends, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from datetime import datetime, timezone
import json

from app.security import (
    hash_password, verify_password, create_access_token, decode_access_token,
    generate_mesh_signature, verify_mesh_signature, encrypt_mesh_payload, decrypt_mesh_payload
)

# La consola clásica de Windows (cp1252) no entiende emojis en los print() de
# alerta de abajo y tira un error 500. Esto la fuerza a UTF-8 al arrancar.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# --- TELEMETRÍA EN TIEMPO REAL (WebSockets) ---
# Lleva la cuenta de qué apps están conectadas al canal de telemetría, para
# poder mandarles mensajes a todas al mismo tiempo (broadcast).
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

DRON_IDS = ["DRON-01", "DRON-02", "DRON-03", "DRON-04", "DRON-05"]

async def simulate_drone_telemetry():
    """Mientras no haya ESP32 real conectado (día 9-11), este bucle manda
    datos de vuelo falsos cada 3 segundos para poder probar la App."""
    while True:
        await asyncio.sleep(3)
        if manager.active_connections:
            telemetria = {
                "event": "TELEMETRIA",
                "dron_id": random.choice(DRON_IDS),
                "bateria_pct": random.randint(35, 100),
                "gps": {
                    "lat": round(21.8823 + random.uniform(-0.002, 0.002), 6),
                    "lng": round(-102.2826 + random.uniform(-0.002, 0.002), 6)
                },
                "estado": random.choice(["PATRULLANDO", "TRATANDO_PLAGA", "REGRESANDO_BASE"]),
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            }
            await manager.broadcast(telemetria)

@asynccontextmanager
async def lifespan(app: FastAPI):
    tarea_telemetria = asyncio.create_task(simulate_drone_telemetry())
    yield
    tarea_telemetria.cancel()

TAGS_METADATA = [
    {
        "name": "Sistema",
        "description": "Estado general del servidor.",
    },
    {
        "name": "Autenticación",
        "description": "Login del rancho y generación del token JWT (Bearer) que se usa en el resto de la API.",
    },
    {
        "name": "Misiones y Enjambre",
        "description": "Despliegue del enjambre de micro-drones sobre un terreno delimitado desde la app.",
    },
    {
        "name": "Ciberseguridad",
        "description": (
            "Kill-switch de emergencia, validación de órdenes del enjambre "
            "(cifrado Fernet + firma HMAC) y bitácora de intentos de intrusión "
            "bloqueados. Esta es la capa que protege al enjambre de drones "
            "clonados o de órdenes falsificadas."
        ),
    },
]

app = FastAPI(
    title="AgroSwarm Shield - Security & Command API",
    description=(
        "Backend de Ciberseguridad Aero-Agrícola y Control de Enjambres "
        "para la red de micro-drones agrícolas biodegradables **AgroSwarm "
        "Shield**.\n\n"
        "Protege la comunicación Servidor ↔ App ↔ Dron con 3 capas:\n"
        "- **JWT** para autenticar a la app del rancho.\n"
        "- **Cifrado Fernet** para que nadie pueda leer las órdenes en tránsito.\n"
        "- **Firma HMAC** para que el dron rechace cualquier orden que no "
        "venga realmente del servidor.\n\n"
        "La telemetría en tiempo real viaja por un canal WebSocket "
        "(`/api/v1/ws/telemetry`), que no aparece en esta documentación "
        "porque OpenAPI/Swagger no soporta WebSockets."
    ),
    version="2.0.0",
    lifespan=lifespan,
    openapi_tags=TAGS_METADATA,
)

# Permite que la App (que corre en otro origen/dominio, ej. un emulador o
# un navegador) pueda llamar a esta API sin que el navegador la bloquee.
# "*" = cualquier origen; está bien para el hackathon porque no usamos
# cookies de sesión (allow_credentials=False), solo el token JWT en el
# header Authorization.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

# Bitácora de intentos de intrusión bloqueados, para poder mostrarla en la
# demo (cuántos ataques se detectaron y de qué tipo).
INTRUSION_LOG: list[dict] = []

async def registrar_intento_intrusion(motivo: str, detalle: str):
    evento = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "motivo": motivo,
        "detalle": detalle
    }
    INTRUSION_LOG.append(evento)
    await manager.broadcast({"event": "INTENTO_INTRUSION", **evento})

# Base de datos simulada para el hackathon
USERS_DB = {
    "rancho_utma": {
        "user_id": "RANCHO-001",
        "username": "rancho_utma",
        "password_hash": hash_password("agrotech2026"),
        "rancho_name": "Rancho San Francisco - Aguascalientes"
    }
}

# Modelos Pydantic (cada uno trae un ejemplo para que se pueda probar
# directamente desde /docs, sin tener que inventar los datos)
class LoginRequest(BaseModel):
    username: str
    password: str

    model_config = {
        "json_schema_extra": {
            "example": {"username": "rancho_utma", "password": "agrotech2026"}
        }
    }

class MissionStartRequest(BaseModel):
    terreno_id: str
    polygon_coordinates: list
    num_drones: int

    model_config = {
        "json_schema_extra": {
            "example": {
                "terreno_id": "TERRENO-AGUASCALIENTES-NORTE",
                "polygon_coordinates": [[21.8823, -102.2826], [21.8830, -102.2810]],
                "num_drones": 5
            }
        }
    }

class KillSwitchRequest(BaseModel):
    reason: str

    model_config = {
        "json_schema_extra": {
            "example": {"reason": "Intento de jamming externo detectado"}
        }
    }

class MeshOrderRequest(BaseModel):
    encrypted_payload: str
    signature: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "encrypted_payload": "gAAAAABlSampleEncryptedPayloadFromMeshNode==",
                "signature": "5d2485089409d913ade486632af259b75380c8d9945a0a3380e61abd34ec608a"
            }
        }
    }

# Middleware de Autenticación JWT
def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de sesión inválido o expirado"
        )
    return payload

# Endpoints REST

@app.get(
    "/",
    tags=["Sistema"],
    summary="Estado del servidor",
)
def root():
    """Revisa rápido si el servidor está en línea, sin necesitar login."""
    return {"status": "ONLINE", "system": "AgroSwarm Shield Cibersecurity Node Activo"}

# 1. LOGIN
@app.post(
    "/api/v1/auth/login",
    tags=["Autenticación"],
    summary="Iniciar sesión del rancho",
    response_description="Token JWT para usar en el resto de la API",
)
def login(credentials: LoginRequest):
    """Valida usuario/contraseña del rancho y entrega un token JWT (Bearer)
    que hay que mandar en el header `Authorization` de los demás endpoints."""
    user = USERS_DB.get(credentials.username)
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Credenciales incorrectas")
    
    token = create_access_token({"sub": user["user_id"], "rancho": user["rancho_name"]})
    return {"access_token": token, "token_type": "bearer", "rancho": user["rancho_name"]}

# 2. DESPLEGAR ENJAMBRE
@app.post(
    "/api/v1/mission/start",
    tags=["Misiones y Enjambre"],
    summary="Desplegar el enjambre sobre un terreno",
    response_description="Confirmación de despliegue + la orden ya cifrada y firmada",
)
async def start_mission(mission: MissionStartRequest, user: dict = Depends(get_current_user)):
    """Recibe el polígono dibujado en la app, genera la orden de despliegue,
    la cifra (Fernet) y la firma (HMAC) para mandarla al enjambre, y avisa
    en vivo por WebSocket a todas las apps conectadas."""
    raw_command = f"DEPLOY:{mission.terreno_id}:{mission.num_drones}"
    signature = generate_mesh_signature(raw_command)
    encrypted_order = encrypt_mesh_payload(raw_command)

    await manager.broadcast({
        "event": "MISION_INICIADA",
        "terreno_id": mission.terreno_id,
        "drones_desplegados": mission.num_drones,
        "timestamp_utc": datetime.now(timezone.utc).isoformat()
    })

    return {
        "status": "MISIÓN_INICIADA",
        "terreno_id": mission.terreno_id,
        "drones_desplegados": mission.num_drones,
        "ciberseguridad": {
            "signature_hmac": signature,
            "encrypted_transmission": encrypted_order
        }
    }

# 3. KILL-SWITCH (0xFF / Cortar Corriente)
@app.post(
    "/api/v1/security/kill-switch",
    tags=["Ciberseguridad"],
    summary="Botón de emergencia: cortar corriente a todos los drones",
    response_description="Confirmación de la orden de paro con su firma HMAC",
)
async def trigger_kill_switch(payload: KillSwitchRequest, user: dict = Depends(get_current_user)):
    """Genera la orden firmada `KILL_SWITCH_ALL_MOTORS_OFF` (opcode 0xFF) y
    la transmite en vivo por WebSocket para que cualquier dron/ESP32
    conectado la reciba, verifique su firma y corte los motores de inmediato."""
    emergency_command = "KILL_SWITCH_ALL_MOTORS_OFF"
    signature = generate_mesh_signature(emergency_command)

    # Manejo seguro de timestamp compatible con Python 3.12+
    now_utc = datetime.now(timezone.utc).isoformat()

    await manager.broadcast({
        "event": "KILL_SWITCH_ACTIVADO",
        "reason": payload.reason,
        "timestamp_utc": now_utc,
        "signature_hmac": signature
    })

    return {
        "status": "EMERGENCY_STOP_ACTIVATED",
        "hardware_opcode": "0xFF",
        "reason": payload.reason,
        "timestamp_utc": now_utc,
        "signature_hmac": signature
    }

# 4. RECEPCIÓN DE ORDEN DESDE EL ENJAMBRE (Validador Anti-Intrusión)
# Este endpoint simula el punto donde el Servidor recibe una orden que dice
# venir de la App o de un nodo Dron/ESP32. No usa JWT porque los nodos ESP32
# no manejan sesiones de usuario: su única prueba de identidad es conocer las
# claves compartidas (Fernet + HMAC) definidas en .env.
@app.post(
    "/api/v1/mesh/order",
    tags=["Ciberseguridad"],
    summary="Recibir orden del enjambre (valida firma y cifrado)",
    response_description="La orden aceptada y descifrada, o un rechazo con alerta de intrusión",
    responses={
        401: {
            "description": "Orden rechazada: paquete corrupto o firma HMAC inválida (posible intrusión)",
        }
    },
)
async def receive_mesh_order(order: MeshOrderRequest):
    """Punto de entrada de cualquier orden que diga venir de un dron/app.
    Primero la descifra (Fernet) y luego verifica su firma (HMAC). Si
    cualquiera de las dos falla, la RECHAZA con código 401 y queda
    registrada en la bitácora de intrusiones."""
    try:
        comando = decrypt_mesh_payload(order.encrypted_payload)
    except Exception:
        motivo = "El paquete cifrado no pudo descifrarse. No proviene de un nodo autorizado."
        print(f"🚨 ALERTA DE INTRUSIÓN: {motivo}")
        await registrar_intento_intrusion("PAQUETE_CIFRADO_INVALIDO", motivo)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": "RECHAZADO",
                "alerta": "INTENTO_DE_INTRUSION_DETECTADO",
                "motivo": motivo
            }
        )

    if not verify_mesh_signature(comando, order.signature):
        motivo = f"La firma HMAC no coincide con el comando '{comando}'. Orden falsificada o alterada."
        print(f"🚨 ALERTA DE INTRUSIÓN: {motivo}")
        await registrar_intento_intrusion("FIRMA_HMAC_INVALIDA", motivo)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": "RECHAZADO",
                "alerta": "INTENTO_DE_INTRUSION_DETECTADO",
                "motivo": motivo
            }
        )

    print(f"✅ Orden del enjambre validada y descifrada: '{comando}'")
    return {
        "status": "ORDEN_ACEPTADA",
        "comando_ejecutado": comando
    }

# 5. BITÁCORA DE INTENTOS DE INTRUSIÓN (para mostrar en la demo)
@app.get(
    "/api/v1/security/intrusion-log",
    tags=["Ciberseguridad"],
    summary="Ver bitácora de intentos de intrusión bloqueados",
    response_description="Total de ataques bloqueados y el detalle de cada uno",
)
def get_intrusion_log(user: dict = Depends(get_current_user)):
    """Devuelve cuántas órdenes falsas ha rechazado `mesh/order` desde que
    arrancó el servidor, con hora, motivo y detalle de cada una."""
    return {
        "total_intentos_bloqueados": len(INTRUSION_LOG),
        "eventos": INTRUSION_LOG
    }

# 6. CANAL DE TELEMETRÍA EN TIEMPO REAL (WebSocket Servidor <-> App)
# La App se conecta una sola vez a este canal y se queda escuchando; el
# servidor le empuja telemetría de los drones y avisos de mission/start y
# kill-switch en el momento en que ocurren, sin que la App tenga que estar
# preguntando ("polling") cada rato.
@app.websocket("/api/v1/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Por ahora no esperamos nada de la App en este canal, pero hay
            # que seguir leyendo para detectar cuándo se desconecta.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)