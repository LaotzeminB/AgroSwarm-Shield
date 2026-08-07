import sys
import asyncio
import math
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
# Lleva la cuenta de qué apps están conectadas al canal de telemetría. Cada
# conexión sabe a qué usuario pertenece (por el token que mandó al conectarse)
# para que la privacidad entre clientes se garantice AQUÍ, del lado del
# servidor -no nada más escondiendo cosas en la pantalla de la app-. Aunque
# dos clientes compartan la misma colmena física, uno nunca debe recibir por
# la red los datos del otro (ni su terreno, ni su posición, ni su estatus).
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.usuario_de_conexion: dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, usuario: str | None = None):
        await websocket.accept()
        self.active_connections.append(websocket)
        if usuario:
            self.usuario_de_conexion[websocket] = usuario

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        self.usuario_de_conexion.pop(websocket, None)

    async def broadcast(self, message: dict):
        """Solo para eventos públicos que no revelan datos privados de
        ningún cliente (la colmena de demostración, la bitácora general de
        intentos de intrusión)."""
        for connection in self.active_connections:
            await connection.send_json(message)

    async def enviar_a_usuarios(self, message: dict, usuarios_permitidos: set):
        """El mensaje llega ÚNICAMENTE a las conexiones de esos usuarios.
        Ni a otros clientes, ni a conexiones anónimas (sin token)."""
        for connection in self.active_connections:
            if self.usuario_de_conexion.get(connection) in usuarios_permitidos:
                await connection.send_json(message)

manager = ConnectionManager()

# Bolsa de posibles drones del enjambre. No todos están activos siempre:
# cada colmena usa los que necesite su terreno en turno, según lo que pida
# la app (los IDs se repiten entre colmenas distintas; cada app solo mira
# los de SU propia colmena, así que no hay confusión).
MAX_DRONES_SIMULADOS = 30
DRON_IDS = [f"DRON-{i:02d}" for i in range(1, MAX_DRONES_SIMULADOS + 1)]

PASOS_DE_VUELO = 6      # cuántos "saltos" tarda en llegar de la base al punto de patrullaje (y de regreso)
PASOS_TRATANDO = 2       # cuántos saltos se queda quieto "tratando la plaga" antes de volver

# --- SERVICIO DE ESCUDO COMPARTIDO ("Shared", criterio CASE del proyecto) ---
# Varios clientes con terrenos vecinos pueden compartir la misma colmena
# solar en vez de tener cada quien la suya: si el terreno nuevo cae dentro
# de este radio de una colmena que ya existe, se une a ella y el enjambre
# reparte su tiempo por turnos entre todos los terrenos de esa colmena. Si
# no hay ninguna cerca, se crea una colmena nueva solo para ese cliente.
RADIO_COMPARTIDO_KM = 2.0
PASOS_POR_TURNO = 8      # cuántos "pasos" de vuelo dura el turno de un terreno antes de rotar al siguiente

def _centroide_poligono(poligono):
    lat_prom = sum(p[0] for p in poligono) / len(poligono)
    lng_prom = sum(p[1] for p in poligono) / len(poligono)
    return lat_prom, lng_prom

def _distancia_km(lat1, lng1, lat2, lng2):
    """Distancia entre dos puntos GPS (fórmula de Haversine), para saber si
    dos terrenos están lo bastante cerca como para compartir colmena."""
    radio_tierra_km = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2)
    return radio_tierra_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

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

def _punto_aleatorio_en_poligono(poligono, limites=None, intentos=30):
    """Prueba puntos al azar dentro del rectángulo que rodea al polígono (o
    dentro de 'limites' si se da, para quedarse en una sola sección) hasta
    encontrar uno que quede realmente adentro de la figura dibujada."""
    if limites:
        lat_min, lat_max, lng_min, lng_max = limites
    else:
        lats = [p[0] for p in poligono]
        lngs = [p[1] for p in poligono]
        lat_min, lat_max, lng_min, lng_max = min(lats), max(lats), min(lngs), max(lngs)

    for _ in range(intentos):
        lat = random.uniform(lat_min, lat_max)
        lng = random.uniform(lng_min, lng_max)
        if _punto_dentro_del_poligono(lat, lng, poligono):
            return lat, lng
    # Esa sección del rectángulo no tiene suficiente terreno adentro del
    # polígono (esquina angosta, etc.): usa el centro de la sección.
    return (lat_min + lat_max) / 2, (lng_min + lng_max) / 2

def _calcular_secciones(poligono, dron_ids):
    """Divide el rectángulo que rodea al terreno en una cuadrícula (una
    celda por dron), para que cada dron patrulle solo su propio cachito y
    nunca se cruce con el de otro."""
    lats = [p[0] for p in poligono]
    lngs = [p[1] for p in poligono]
    lat_min, lat_max = min(lats), max(lats)
    lng_min, lng_max = min(lngs), max(lngs)

    n = len(dron_ids)
    columnas = max(1, math.ceil(math.sqrt(n)))
    filas = max(1, math.ceil(n / columnas))
    ancho_lat = (lat_max - lat_min) / filas
    ancho_lng = (lng_max - lng_min) / columnas

    secciones = {}
    for indice, dron_id in enumerate(dron_ids):
        fila = indice // columnas
        columna = indice % columnas
        seccion_lat_min = lat_min + fila * ancho_lat
        seccion_lng_min = lng_min + columna * ancho_lng
        secciones[dron_id] = (
            seccion_lat_min, seccion_lat_min + ancho_lat,
            seccion_lng_min, seccion_lng_min + ancho_lng
        )
    return secciones

def _terreno_en_turno(colmena):
    """El terreno que está siendo patrullado ahora mismo en esa colmena."""
    if not colmena["terrenos"]:
        return None
    return colmena["terrenos"][colmena["indice_terreno_actual"]]

def _nuevo_objetivo_patrullaje(colmena, dron_id):
    """Elige un punto al azar para que el dron vuele hacia allá: dentro de
    SU sección del terreno que esté en turno ahorita."""
    terreno = _terreno_en_turno(colmena)
    if terreno:
        limites = colmena["secciones"].get(dron_id)
        return _punto_aleatorio_en_poligono(terreno["poligono"], limites=limites)
    return (
        colmena["lat"] + random.uniform(-0.003, 0.003),
        colmena["lng"] + random.uniform(-0.003, 0.003)
    )

def _estado_inicial_dron(colmena, dron_id):
    lat_objetivo, lng_objetivo = _nuevo_objetivo_patrullaje(colmena, dron_id)
    return {
        "dron_id": dron_id,
        "lat": colmena["lat"],
        "lng": colmena["lng"],
        "objetivo_lat": lat_objetivo,
        "objetivo_lng": lng_objetivo,
        "fase": "PATRULLANDO",       # PATRULLANDO (saliendo) -> TRATANDO_PLAGA -> REGRESANDO_BASE
        "pasos_restantes": PASOS_DE_VUELO,
        "bateria_pct": 100
    }

def _avanzar_dron(colmena, estado: dict) -> dict:
    """Mueve un dron un paso dentro de su ciclo: sale de la colmena,
    patrulla/trata la plaga, y regresa a recargar. Al llegar a la base
    vuelve a salir hacia un punto nuevo, en un ciclo infinito."""
    base_lat, base_lng = colmena["lat"], colmena["lng"]

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
            if colmena["detenido"]:
                # Kill-switch activo: se queda aterrizado hasta la próxima misión.
                estado["fase"] = "EN_BASE"
            else:
                # Vuelo normal: recarga y sale de nuevo hacia un punto nuevo
                # (dentro de su misma sección del terreno en turno).
                estado["objetivo_lat"], estado["objetivo_lng"] = _nuevo_objetivo_patrullaje(colmena, estado["dron_id"])
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

def _estado_desfasado_al_azar(colmena, dron_id) -> dict:
    """Crea un dron ya 'en vuelo', adelantado un número al azar de pasos
    dentro de su ciclo, para que el enjambre no salga siempre en bloque
    desde la colmena."""
    estado = _estado_inicial_dron(colmena, dron_id)
    largo_del_ciclo = PASOS_DE_VUELO + PASOS_TRATANDO + PASOS_DE_VUELO
    for _ in range(random.randint(0, largo_del_ciclo - 1)):
        _avanzar_dron(colmena, estado)
    return estado

def _asignar_drones_para_terreno(colmena):
    """(Re)activa el enjambre de una colmena para que patrulle el terreno
    que esté en turno ahorita, con el número de drones que ese cliente pidió
    (topado al máximo de la simulación)."""
    terreno = _terreno_en_turno(colmena)
    if not terreno:
        colmena["drones_activos"] = []
        colmena["secciones"] = {}
        return
    num = max(1, min(terreno["num_drones"], MAX_DRONES_SIMULADOS))
    ids_nuevos = DRON_IDS[:num]
    colmena["drones_activos"] = ids_nuevos
    colmena["secciones"] = _calcular_secciones(terreno["poligono"], ids_nuevos)
    for dron_id in ids_nuevos:
        colmena["enjambre"][dron_id] = _estado_desfasado_al_azar(colmena, dron_id)

def _nueva_colmena(colmena_id, lat, lng, es_demo=False):
    return {
        "colmena_id": colmena_id,
        "lat": lat,
        "lng": lng,
        "es_demo": es_demo,
        "terrenos": [],              # cada uno: {terreno_id, usuario, poligono, num_drones}
        "indice_terreno_actual": 0,
        "pasos_en_turno_actual": 0,
        "drones_activos": [],
        "secciones": {},
        "detenido": False,
        "enjambre": {}
    }

def _asignar_colmena(terreno_id, usuario, poligono, num_drones):
    """Busca una colmena real ya existente lo bastante cerca del terreno
    nuevo para compartirla; si no hay ninguna, crea una colmena nueva solo
    para este cliente. Devuelve (colmena, compartida)."""
    centro_lat, centro_lng = _centroide_poligono(poligono)

    # Si este mismo usuario ya tenía un terreno en alguna colmena, se le
    # quita de ahí primero (para no dejarlo duplicado si vuelve a desplegar).
    for colmena in COLMENAS.values():
        colmena["terrenos"] = [t for t in colmena["terrenos"] if t["usuario"] != usuario]

    # Borra colmenas reales que se quedaron sin ningún cliente.
    for cid in [c for c, colm in COLMENAS.items() if not colm["terrenos"] and not colm.get("es_demo")]:
        del COLMENAS[cid]

    mejor_colmena, menor_distancia = None, None
    for colmena in COLMENAS.values():
        if colmena.get("es_demo"):
            continue
        distancia = _distancia_km(centro_lat, centro_lng, colmena["lat"], colmena["lng"])
        if distancia <= RADIO_COMPARTIDO_KM and (menor_distancia is None or distancia < menor_distancia):
            mejor_colmena, menor_distancia = colmena, distancia

    nuevo_terreno = {"terreno_id": terreno_id, "usuario": usuario, "poligono": poligono, "num_drones": num_drones}

    if mejor_colmena:
        mejor_colmena["terrenos"].append(nuevo_terreno)
        # La colmena se reacomoda al centro de todos los terrenos que atiende.
        lats = [_centroide_poligono(t["poligono"])[0] for t in mejor_colmena["terrenos"]]
        lngs = [_centroide_poligono(t["poligono"])[1] for t in mejor_colmena["terrenos"]]
        mejor_colmena["lat"] = sum(lats) / len(lats)
        mejor_colmena["lng"] = sum(lngs) / len(lngs)
        return mejor_colmena, len(mejor_colmena["terrenos"]) > 1

    nueva_id = f"COLMENA-{len(COLMENAS) + 1:02d}"
    nueva = _nueva_colmena(nueva_id, centro_lat, centro_lng)
    nueva["terrenos"].append(nuevo_terreno)
    COLMENAS[nueva_id] = nueva
    return nueva, False

async def _rotar_turno(colmena):
    """Le toca el turno de patrullaje al siguiente terreno que comparte esa
    colmena. Cada cliente de esa colmena recibe SOLO un aviso sobre sí mismo
    (si ya le toca o sigue esperando) -nunca el nombre ni el terreno del
    cliente que sí está en turno, para no revelar el estatus de nadie más."""
    colmena["indice_terreno_actual"] = (colmena["indice_terreno_actual"] + 1) % len(colmena["terrenos"])
    colmena["pasos_en_turno_actual"] = 0
    _asignar_drones_para_terreno(colmena)
    terreno_en_turno = _terreno_en_turno(colmena)
    for terreno in colmena["terrenos"]:
        await manager.enviar_a_usuarios({
            "event": "TURNO_ROTADO",
            "colmena_id": colmena["colmena_id"],
            "es_tu_turno": terreno["usuario"] == terreno_en_turno["usuario"],
            "terrenos_compartiendo_colmena": len(colmena["terrenos"]),
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }, {terreno["usuario"]})

# Colmenas activas en memoria (colmena_id -> datos). Empieza con una colmena
# de demostración (para que siempre haya algo de actividad en el mapa,
# incluso antes de que un cliente real despliegue su primer terreno). Las
# colmenas reales las crea/comparte "mission/start" según dónde caiga cada
# terreno.
COLMENAS = {}
_colmena_demo = _nueva_colmena("COLMENA-DEMO", 21.8823, -102.2826, es_demo=True)
_colmena_demo["terrenos"].append({
    "terreno_id": "DEMO",
    "usuario": "demo",
    "poligono": [
        [21.8823 - 0.003, -102.2826 - 0.003], [21.8823 + 0.003, -102.2826 - 0.003],
        [21.8823 + 0.003, -102.2826 + 0.003], [21.8823 - 0.003, -102.2826 + 0.003]
    ],
    "num_drones": 5
})
COLMENAS["COLMENA-DEMO"] = _colmena_demo
_asignar_drones_para_terreno(COLMENAS["COLMENA-DEMO"])

async def simulate_drone_telemetry():
    """Mientras no haya ESP32 real conectado (día 9-11), este bucle mueve a
    cada dron activo de cada colmena un paso de su vuelo (colmena ->
    patrullaje -> colmena) y transmite su posición, para que la app pueda
    animarlos en el mapa. Si una colmena atiende a más de un cliente, va
    rotando de cuál terreno es el turno."""
    while True:
        await asyncio.sleep(2.5)
        if manager.active_connections:
            for colmena in list(COLMENAS.values()):
                terreno_en_turno = _terreno_en_turno(colmena)
                for dron_id in colmena["drones_activos"]:
                    estado = _avanzar_dron(colmena, colmena["enjambre"][dron_id])
                    telemetria = {
                        "event": "TELEMETRIA",
                        "colmena_id": colmena["colmena_id"],
                        "dron_id": dron_id,
                        "bateria_pct": estado["bateria_pct"],
                        "gps": {
                            "lat": round(estado["lat"], 6),
                            "lng": round(estado["lng"], 6)
                        },
                        "estado": estado["fase"],
                        "timestamp_utc": datetime.now(timezone.utc).isoformat()
                    }
                    if colmena.get("es_demo"):
                        # La colmena de demostración no tiene datos privados
                        # de ningún cliente real: se puede ver públicamente.
                        await manager.broadcast(telemetria)
                    elif terreno_en_turno:
                        # Solo le llega al cliente cuyo terreno está en turno
                        # ahora mismo -ni siquiera a los demás que comparten
                        # la misma colmena- porque esas coordenadas son de SU
                        # terreno, no del de nadie más.
                        await manager.enviar_a_usuarios(telemetria, {terreno_en_turno["usuario"]})
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

                if len(colmena["terrenos"]) > 1 and not colmena["detenido"]:
                    colmena["pasos_en_turno_actual"] += 1
                    if colmena["pasos_en_turno_actual"] >= PASOS_POR_TURNO:
                        await _rotar_turno(colmena)

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
    colmena_id: str | None = None  # si se omite, el kill-switch para TODAS las colmenas (paro general)

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
    """Recibe el polígono dibujado en la app y busca (o crea) la colmena que
    le corresponde: si hay una colmena real cerca, este terreno se une a ella
    y comparte el enjambre con quien ya estuviera ahí (turnándose); si no hay
    ninguna cerca, se crea una colmena nueva solo para este cliente. También
    genera la orden de despliegue cifrada (Fernet) y firmada (HMAC), y avisa
    por WebSocket -solo a este cliente, nunca a los demás- que ya se desplegó."""
    usuario_id = user.get("sub", "desconocido")

    if not mission.polygon_coordinates or len(mission.polygon_coordinates) < 3:
        raise HTTPException(status_code=400, detail="Se necesita un polígono con al menos 3 puntos")

    num_drones_pedidos = max(1, min(mission.num_drones, MAX_DRONES_SIMULADOS))
    colmena, compartida = _asignar_colmena(
        mission.terreno_id, usuario_id, mission.polygon_coordinates, num_drones_pedidos
    )
    colmena["detenido"] = False

    # De cortesía, el terreno recién desplegado entra de inmediato en turno
    # (no tiene que esperar a que le toque, como si fuera nuevo en la fila).
    for indice, terreno in enumerate(colmena["terrenos"]):
        if terreno["terreno_id"] == mission.terreno_id:
            colmena["indice_terreno_actual"] = indice
            break
    colmena["pasos_en_turno_actual"] = 0
    _asignar_drones_para_terreno(colmena)

    raw_command = f"DEPLOY:{mission.terreno_id}:{num_drones_pedidos}"
    signature = generate_mesh_signature(raw_command)
    encrypted_order = encrypt_mesh_payload(raw_command)

    drones_desplegados = len(colmena["drones_activos"])

    # Este aviso es PRIVADO: solo le llega al cliente que acaba de desplegar,
    # nunca a otros clientes que compartan la misma colmena.
    await manager.enviar_a_usuarios({
        "event": "MISION_INICIADA",
        "colmena_id": colmena["colmena_id"],
        "terreno_id": mission.terreno_id,
        "drones_desplegados": drones_desplegados,
        "colmena": {"lat": colmena["lat"], "lng": colmena["lng"]},
        "compartida": compartida,
        "terrenos_en_colmena": len(colmena["terrenos"]),
        "timestamp_utc": datetime.now(timezone.utc).isoformat()
    }, {usuario_id})

    # Si este terreno se unió a una colmena que ya tenía otros clientes, se
    # les "quitó" el turno de golpe por la cortesía de arriba -así que se les
    # avisa de inmediato (sin esperar a la siguiente rotación automática) de
    # que ahora es compartida y no es su turno, sin decirles de quién es el
    # terreno nuevo ni dónde está.
    if compartida:
        for terreno in colmena["terrenos"]:
            if terreno["usuario"] == usuario_id:
                continue
            await manager.enviar_a_usuarios({
                "event": "TURNO_ROTADO",
                "colmena_id": colmena["colmena_id"],
                "es_tu_turno": False,
                "terrenos_compartiendo_colmena": len(colmena["terrenos"]),
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            }, {terreno["usuario"]})

    return {
        "status": "MISIÓN_INICIADA",
        "colmena_id": colmena["colmena_id"],
        "terreno_id": mission.terreno_id,
        "drones_desplegados": drones_desplegados,
        "drones_pedidos": mission.num_drones,
        "compartida": compartida,
        "terrenos_en_colmena": len(colmena["terrenos"]),
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
    En la simulación, esto hace que el enjambre de la colmena regrese
    volando y se quede aterrizado ahí hasta la siguiente misión.

    Por seguridad, un cliente solo puede apagar colmenas donde ÉL tenga un
    terreno -nunca la de otro cliente, aunque le pase su colmena_id a mano-.
    Si no manda colmena_id, se apagan todas las colmenas donde el usuario
    tenga algo desplegado (pero jamás las de otros clientes)."""
    usuario_id = user.get("sub", "desconocido")

    if payload.colmena_id:
        colmena = COLMENAS.get(payload.colmena_id)
        if not colmena or not any(t["usuario"] == usuario_id for t in colmena["terrenos"]):
            raise HTTPException(status_code=403, detail="Esa colmena no tiene ningún terreno tuyo")
        colmenas_afectadas = [colmena]
    else:
        colmenas_afectadas = [
            c for c in COLMENAS.values() if any(t["usuario"] == usuario_id for t in c["terrenos"])
        ]

    emergency_command = "KILL_SWITCH_ALL_MOTORS_OFF"
    signature = generate_mesh_signature(emergency_command)
    now_utc = datetime.now(timezone.utc).isoformat()

    for colmena in colmenas_afectadas:
        colmena["detenido"] = True
        for dron_id in colmena["drones_activos"]:
            _forzar_regreso_a_base(colmena["enjambre"][dron_id])

        usuarios_afectados = {t["usuario"] for t in colmena["terrenos"]}
        await manager.enviar_a_usuarios({
            "event": "KILL_SWITCH_ACTIVADO",
            "colmena_id": colmena["colmena_id"],
            "reason": payload.reason,
            "timestamp_utc": now_utc,
            "signature_hmac": signature
        }, usuarios_afectados)

    return {
        "status": "EMERGENCY_STOP_ACTIVATED",
        "hardware_opcode": "0xFF",
        "colmenas_detenidas": [c["colmena_id"] for c in colmenas_afectadas],
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
# preguntando ("polling") cada rato. Manda su token de sesión como parámetro
# (?token=...) para que el servidor sepa qué cliente es y solo le mande SUS
# propios datos, aunque comparta colmena con otros clientes.
@app.websocket("/api/v1/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket, token: str | None = None):
    usuario = None
    if token:
        payload = decode_access_token(token)
        if payload:
            usuario = payload.get("sub")
    await manager.connect(websocket, usuario)
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