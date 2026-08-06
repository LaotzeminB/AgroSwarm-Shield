import os
from pymongo import MongoClient

# Misma base de datos que usa el proyecto de Richard (AbejitaSimple): así
# los usuarios, la bitácora de intrusiones y la telemetría del enjambre
# quedan guardados de verdad (ya no se pierden al reiniciar el servidor).
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")

_cliente = MongoClient(MONGO_URI)
db = _cliente["AbejitaDB"]

usuarios_col = db["Usuarios"]
intrusiones_col = db["IntrusionLog"]
telemetria_col = db["Telemetria"]


def verificar_conexion() -> bool:
    """Revisa si MongoDB responde. No detiene el servidor si falla, solo
    avisa en consola (igual que hace el proyecto de Richard en C#)."""
    try:
        _cliente.admin.command("ping")
        print("MongoDB: conexión establecida correctamente (base de datos 'AbejitaDB').")
        return True
    except Exception as error:
        print(
            "MongoDB: no se pudo conectar - "
            f"{error}. Verifica que el servicio 'MongoDB' esté corriendo "
            "en esta máquina (services.msc -> MongoDB Server)."
        )
        return False
