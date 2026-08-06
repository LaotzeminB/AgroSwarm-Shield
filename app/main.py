import sys
import asyncio
import random
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Depends, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from datetime import datetime, timezone
import json

from app.security import (
    hash_password, verify_password, create_access_token, decode_access_token,
    generate_mesh_signature, verify_mesh_signature, encrypt_mesh_payload, decrypt_mesh_payload
)
from app.database import usuarios_col, intrusiones_col, telemetria_col, verificar_conexion
from bson import ObjectId

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

# Bolsa de posibles drones del enjambre. No todos están activos siempre:
# "mission/start" decide cuántos de estos se usan, según lo que pida la app.
MAX_DRONES_SIMULADOS = 30
DRON_IDS = [f"DRON-{i:02d}" for i in range(1, MAX_DRONES_SIMULADOS + 1)]

# Colmena solar: punto de partida y regreso de todo el enjambre. Empieza en
# Aguascalientes por defecto, pero se mueve al centro del terreno en cuanto
# alguien dibuja un polígono y presiona "Desplegar Escudo".
PASOS_DE_VUELO = 6      # cuántos "saltos" tarda en llegar de la base al punto de patrullaje (y de regreso)
PASOS_TRATANDO = 2       # cuántos saltos se queda quieto "tratando la plaga" antes de volver

MISION_ACTIVA = {
    "poligono": None,               # lista de [lat, lng] del terreno dibujado, o None si no se ha desplegado nada
    "base_lat": 21.8823,
    "base_lng": -102.2826,
    "drones_activos": DRON_IDS[:5],  # antes de desplegar nada, se muestran 5 de ejemplo
    "detenido": False                # True mientras el kill-switch esté activo (drones aterrizados)
}

def _centroide_poligono(poligono):
    lat_prom = sum(p[0] for p in poligono) / len(poligono)
    lng_prom = sum(p[1] for p in poligono) / len(poligono)
    return lat_prom, lng_prom

def _punto_dentro_del_poligono(lat, lng, poligono):
    """Algoritmo de 'ray casting': cuenta cuántas veces una línea horizontal
    desde el punto cruza los bordes del polígono. Si cruza un número impar
    de veces, el punto está adentro."""
    dentro = False
    n = len(poligono)
    for i in range(n):
        lat1, lng1 = poligono[i]
        lat2, lng2 = poligono[(i + 1) % n]
        if (lng1 > lng) != (lng2 > lng):
            lat_interseccion = lat1 + (lat2 - lat1) * (lng - lng1) / (lng2 - lng1)
            if lat < lat_interseccion:
                dentro = not dentro
    return dentro

def _punto_aleatorio_en_poligono(poligono, intentos=30):
    """Prueba puntos al azar dentro del rectángulo que rodea al polígono
    hasta encontrar uno que quede realmente adentro de la figura dibujada."""
    lats = [p[0] for p in poligono]
    lngs = [p[1] for p in poligono]
    for _ in range(intentos):
        lat = random.uniform(min(lats), max(lats))
        lng = random.uniform(min(lngs), max(lngs))
        if _punto_dentro_del_poligono(lat, lng, poligono):
            return lat, lng
    return _centroide_poligono(poligono)  # polígono muy angosto: usa el centro

def _nuevo_objetivo_patrullaje():
    """Elige un punto al azar dentro del terreno dibujado para que el dron
    vuele hacia allá. Si todavía no se ha desplegado ningún terreno, patrulla
    cerca de la colmena por defecto."""
    poligono = MISION_ACTIVA["poligono"]
    if poligono and len(poligono) >= 3:
        return _punto_aleatorio_en_poligono(poligono)
    return (
        MISION_ACTIVA["base_lat"] + random.uniform(-0.003, 0.003),
        MISION_ACTIVA["base_lng"] + random.uniform(-0.003, 0.003)
    )

def _estado_inicial_dron():
    lat_objetivo, lng_objetivo = _nuevo_objetivo_patrullaje()
    return {
        "lat": MISION_ACTIVA["base_lat"],
        "lng": MISION_ACTIVA["base_lng"],
        "objetivo_lat": lat_objetivo,
        "objetivo_lng": lng_objetivo,
        "fase": "PATRULLANDO",       # PATRULLANDO (saliendo) -> TRATANDO_PLAGA -> REGRESANDO_BASE
        "pasos_restantes": PASOS_DE_VUELO,
        "bateria_pct": 100
    }

def _avanzar_dron(estado: dict) -> dict:
    """Mueve un dron un paso dentro de su ciclo: sale de la colmena,
    patrulla/trata la plaga, y regresa a recargar. Al llegar a la base
    vuelve a salir hacia un punto nuevo, en un ciclo infinito."""
    base_lat, base_lng = MISION_ACTIVA["base_lat"], MISION_ACTIVA["base_lng"]

    if estado["fase"] == "PATRULLANDO":
        fraccion = 1 - (estado["pasos_restantes"] - 1) / PASOS_DE_VUELO
        estado["lat"] = base_lat + (estado["objetivo_lat"] - base_lat) * fraccion
        estado["lng"] = base_lng + (estado["objetivo_lng"] - base_lng) * fraccion
        estado["bateria_pct"] = max(15, estado["bateria_pct"] - random.randint(2, 5))
        estado["pasos_restantes"] -= 1
        if estado["pasos_restantes"] <= 0:
            estado["fase"] = "TRATANDO_PLAGA"
            estado["pasos_restantes"] = PASOS_TRATANDO

    elif estado["fase"] == "TRATANDO_PLAGA":
        estado["bateria_pct"] = max(15, estado["bateria_pct"] - 1)
        estado["pasos_restantes"] -= 1
        if estado["pasos_restantes"] <= 0:
            estado["fase"] = "REGRESANDO_BASE"
            estado["pasos_restantes"] = PASOS_DE_VUELO

    elif estado["fase"] == "REGRESANDO_BASE":
        fraccion = 1 - (estado["pasos_restantes"] - 1) / PASOS_DE_VUELO
        estado["lat"] = estado["objetivo_lat"] + (base_lat - estado["objetivo_lat"]) * fraccion
        estado["lng"] = estado["objetivo_lng"] + (base_lng - estado["objetivo_lng"]) * fraccion
        estado["bateria_pct"] = max(15, estado["bateria_pct"] - random.randint(2, 5))
        estado["pasos_restantes"] -= 1
        if estado["pasos_restantes"] <= 0:
            # Llegó a la colmena: recarga.
            estado["lat"], estado["lng"] = base_lat, base_lng
            estado["bateria_pct"] = 100
            if MISION_ACTIVA["detenido"]:
                # Kill-switch activo: se queda aterrizado hasta la próxima misión.
                estado["fase"] = "EN_BASE"
            else:
                # Vuelo normal: recarga y sale de nuevo hacia un punto nuevo.
                estado["objetivo_lat"], estado["objetivo_lng"] = _nuevo_objetivo_patrullaje()
                estado["fase"] = "PATRULLANDO"
                estado["pasos_restantes"] = PASOS_DE_VUELO

    # "EN_BASE": el dron está aterrizado con los motores cortados, no se mueve
    # hasta que se despliegue una misión nueva.

    return estado

def _forzar_regreso_a_base(estado: dict) -> dict:
    """Usado por el kill-switch: interrumpe lo que esté haciendo el dron y lo
    manda de regreso a la colmena desde su posición actual (no desde donde
    haya empezado a patrullar)."""
    estado["objetivo_lat"], estado["objetivo_lng"] = estado["lat"], estado["lng"]
    estado["fase"] = "REGRESANDO_BASE"
    estado["pasos_restantes"] = PASOS_DE_VUELO
    return estado

def _estado_desfasado_al_azar() -> dict:
    """Crea un dron ya 'en vuelo', adelantado un número al azar de pasos
    dentro de su ciclo, para que el enjambre no salga siempre en bloque
    desde la colmena al arrancar el servidor."""
    estado = _estado_inicial_dron()
    largo_del_ciclo = PASOS_DE_VUELO + PASOS_TRATANDO + PASOS_DE_VUELO
    for _ in range(random.randint(0, largo_del_ciclo - 1)):
        _avanzar_dron(estado)
    return estado

# Estado en memoria de cada dron del enjambre (posición real, no aleatoria
# en cada tick, para que la animación se vea como un vuelo continuo). Solo
# se llenan los que están activos; el resto de la bolsa (DRON_IDS) se crea
# hasta que "mission/start" los active.
ENJAMBRE = {dron_id: _estado_desfasado_al_azar() for dron_id in MISION_ACTIVA["drones_activos"]}

async def simulate_drone_telemetry():
    """Mientras no haya ESP32 real conectado (día 9-11), este bucle mueve a
    cada dron activo un paso de su vuelo (colmena -> patrullaje -> colmena) y
    transmite su posición, para que la app pueda animarlos en el mapa."""
    while True:
        await asyncio.sleep(2.5)
        if manager.active_connections:
            for dron_id in MISION_ACTIVA["drones_activos"]:
                estado = _avanzar_dron(ENJAMBRE[dron_id])
                telemetria = {
                    "event": "TELEMETRIA",
                    "dron_id": dron_id,
                    "bateria_pct": estado["bateria_pct"],
                    "gps": {
                        "lat": round(estado["lat"], 6),
                        "lng": round(estado["lng"], 6)
                    },
                    "estado": estado["fase"],
                    "timestamp_utc": datetime.now(timezone.utc).isoformat()
                }
                await manager.broadcast(telemetria)
                # Nota: esta telemetría (posición de vuelo simulada del
                # enjambre) NO se guarda en la colección "Telemetria" de
                # Mongo, porque esa colección es la que llena de verdad el
                # sensor de campo de Richard (AbejitaSimple, en C#). Guardar
                # ahí también los datos de esta simulación duplicaría/
                # mezclaría dos fuentes distintas de datos en el mismo lugar.
                # En vez de eso, este backend LEE esa colección para
                # reaccionar a sus detecciones reales (ver
                # escuchar_sensores_richard más abajo) — así los dos
                # programas quedan coordinados en vez de competir.

async def escuchar_sensores_richard():
    """Lee la colección 'Telemetria' de MongoDB que llena en vivo el
    proyecto de Richard (AbejitaSimple, en C#/.NET) y, en cuanto su sensor
    reporta una plaga detectada, lo avisa por WebSocket a todas las apps
    conectadas. Con esto los dos programas quedan genuinamente coordinados:
    uno genera los datos del sensor, el otro los escucha y reacciona -en vez
    de que cada quien invente su propia telemetría por separado."""
    ultimo_id_visto = ObjectId.from_datetime(datetime.now(timezone.utc))
    while True:
        await asyncio.sleep(3)
        try:
            nuevas_detecciones = await run_in_threadpool(
                lambda: list(telemetria_col.find({
                    "plagaDetectada": True,
                    "_id": {"$gt": ultimo_id_visto}
                }).sort("_id", 1))
            )
        except Exception as error:
            print(f"No se pudo leer la telemetría del sensor de Richard: {error}")
            continue

        for deteccion in nuevas_detecciones:
            ultimo_id_visto = deteccion["_id"]
            await manager.broadcast({
                "event": "PLAGA_DETECTADA_SENSOR",
                "lat": deteccion.get("lat"),
                "lng": deteccion.get("lon"),
                "altura": deteccion.get("altura"),
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })

@asynccontextmanager
async def lifespan(app: FastAPI):
    verificar_conexion()
    _sembrar_usuario_demo()
    tarea_telemetria = asyncio.create_task(simulate_drone_telemetry())
    tarea_sensores = asyncio.create_task(escuchar_sensores_richard())
    yield
    tarea_telemetria.cancel()
    tarea_sensores.cancel()

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

# Bitácora de intentos de intrusión bloqueados (guardada en MongoDB, colección
# "IntrusionLog"), para poder mostrarla en la demo y que no se pierda si se
# reinicia el servidor.
async def registrar_intento_intrusion(motivo: str, detalle: str):
    evento = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "motivo": motivo,
        "detalle": detalle
    }
    await run_in_threadpool(intrusiones_col.insert_one, dict(evento))
    await manager.broadcast({"event": "INTENTO_INTRUSION", **evento})

def _sembrar_usuario_demo():
    """Si la base de datos está vacía (por ejemplo, la primera vez que se
    corre el servidor en una máquina nueva del equipo), crea el usuario de
    prueba de siempre para que el panel funcione sin configurar nada."""
    if usuarios_col.find_one({"username": "rancho_utma"}) is None:
        usuarios_col.insert_one({
            "user_id": "RANCHO-001",
            "username": "rancho_utma",
            "password_hash": hash_password("agrotech2026"),
            "rancho_name": "Rancho San Francisco - Aguascalientes"
        })

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

class RegisterRequest(BaseModel):
    username: str
    password: str
    rancho_name: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "username": "rancho_nuevo",
                "password": "unaClaveSegura123",
                "rancho_name": "Rancho Los Alamos - Aguascalientes"
            }
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
    """Valida usuario/contraseña del rancho (contra MongoDB) y entrega un
    token JWT (Bearer) que hay que mandar en el header `Authorization` de
    los demás endpoints."""
    user = usuarios_col.find_one({"username": credentials.username})
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Credenciales incorrectas")

    token = create_access_token({"sub": user["user_id"], "rancho": user["rancho_name"]})
    return {"access_token": token, "token_type": "bearer", "rancho": user["rancho_name"]}

# 1B. REGISTRO DE UN RANCHO NUEVO
# Los usuarios se guardan en MongoDB (colección "Usuarios", misma base de
# datos "AbejitaDB" que usa el proyecto de Richard), así que ya no se
# pierden si el servidor se reinicia.
@app.post(
    "/api/v1/auth/register",
    tags=["Autenticación"],
    summary="Registrar un rancho nuevo",
    response_description="Token JWT del rancho recién creado (inicia sesión automáticamente)",
)
def register(datos: RegisterRequest):
    """Crea una cuenta nueva de rancho y entrega de una vez su token JWT,
    para no obligar al usuario a iniciar sesión otra vez después de
    registrarse."""
    if usuarios_col.find_one({"username": datos.username}) is not None:
        raise HTTPException(status_code=400, detail="Ese nombre de usuario ya está en uso")

    if len(datos.password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")

    user_id = f"RANCHO-{usuarios_col.count_documents({}) + 1:03d}"
    usuarios_col.insert_one({
        "user_id": user_id,
        "username": datos.username,
        "password_hash": hash_password(datos.password),
        "rancho_name": datos.rancho_name
    })

    token = create_access_token({"sub": user_id, "rancho": datos.rancho_name})
    return {"access_token": token, "token_type": "bearer", "rancho": datos.rancho_name}

# 2. DESPLEGAR ENJAMBRE
@app.post(
    "/api/v1/mission/start",
    tags=["Misiones y Enjambre"],
    summary="Desplegar el enjambre sobre un terreno",
    response_description="Confirmación de despliegue + la orden ya cifrada y firmada",
)
async def start_mission(mission: MissionStartRequest, user: dict = Depends(get_current_user)):
    """Recibe el polígono dibujado en la app, mueve la colmena al centro de
    ese terreno, activa el número de drones pedido (según lo que quepa en la
    bolsa de simulación) y hace que patrullen dentro de la figura dibujada.
    También genera la orden de despliegue cifrada (Fernet) y firmada (HMAC)
    para el enjambre, y avisa en vivo por WebSocket a todas las apps."""
    if mission.polygon_coordinates and len(mission.polygon_coordinates) >= 3:
        MISION_ACTIVA["poligono"] = mission.polygon_coordinates
        MISION_ACTIVA["base_lat"], MISION_ACTIVA["base_lng"] = _centroide_poligono(mission.polygon_coordinates)

    num_drones_activos = max(1, min(mission.num_drones, MAX_DRONES_SIMULADOS))
    MISION_ACTIVA["drones_activos"] = DRON_IDS[:num_drones_activos]
    MISION_ACTIVA["detenido"] = False

    # Reinicia a cada dron activo desde la colmena (nueva o de siempre) para
    # que salgan a patrullar el terreno recién marcado.
    for dron_id in MISION_ACTIVA["drones_activos"]:
        ENJAMBRE[dron_id] = _estado_desfasado_al_azar()

    raw_command = f"DEPLOY:{mission.terreno_id}:{num_drones_activos}"
    signature = generate_mesh_signature(raw_command)
    encrypted_order = encrypt_mesh_payload(raw_command)

    await manager.broadcast({
        "event": "MISION_INICIADA",
        "terreno_id": mission.terreno_id,
        "drones_desplegados": num_drones_activos,
        "colmena": {"lat": MISION_ACTIVA["base_lat"], "lng": MISION_ACTIVA["base_lng"]},
        "timestamp_utc": datetime.now(timezone.utc).isoformat()
    })

    return {
        "status": "MISIÓN_INICIADA",
        "terreno_id": mission.terreno_id,
        "drones_desplegados": num_drones_activos,
        "drones_pedidos": mission.num_drones,
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
    conectado la reciba, verifique su firma y corte los motores de inmediato.
    En la simulación, esto hace que todo el enjambre regrese volando a la
    colmena y se quede aterrizado ahí hasta la siguiente misión."""
    MISION_ACTIVA["detenido"] = True
    for dron_id in MISION_ACTIVA["drones_activos"]:
        _forzar_regreso_a_base(ENJAMBRE[dron_id])

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
    """Devuelve cuántas órdenes falsas ha rechazado `mesh/order` desde
    siempre (queda guardado en MongoDB), con hora, motivo y detalle de
    cada una, la más reciente primero."""
    eventos = list(
        intrusiones_col.find({}, {"_id": 0}).sort("timestamp_utc", -1)
    )
    return {
        "total_intentos_bloqueados": intrusiones_col.count_documents({}),
        "eventos": eventos
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

# --- PANEL WEB (mientras la app móvil de Gus no esté disponible) ---
# Sirve el panel de control en /panel: login, mapa, despliegue del enjambre,
# kill-switch y telemetría en vivo, todo hablando con esta misma API.
@app.get("/panel", include_in_schema=False)
def ir_al_panel():
    return RedirectResponse(url="/panel/index.html")

app.mount("/panel", StaticFiles(directory="app/static", html=True), name="panel")