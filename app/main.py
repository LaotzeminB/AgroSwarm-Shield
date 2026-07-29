from fastapi import FastAPI, HTTPException, Header, Depends, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from datetime import datetime, timezone
import json

from app.security import (
    hash_password, verify_password, create_access_token, decode_access_token,
    generate_mesh_signature, verify_mesh_signature, encrypt_mesh_payload
)

app = FastAPI(
    title="AgroSwarm Shield - Security & Command API",
    description="Backend de Ciberseguridad Aero-Agrícola y Control de Enjambres",
    version="2.0.0"
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

# Base de datos simulada para el hackathon
USERS_DB = {
    "rancho_utma": {
        "user_id": "RANCHO-001",
        "username": "rancho_utma",
        "password_hash": hash_password("agrotech2026"),
        "rancho_name": "Rancho San Francisco - Aguascalientes"
    }
}

# Modelos Pydantic
class LoginRequest(BaseModel):
    username: str
    password: str

class MissionStartRequest(BaseModel):
    terreno_id: str
    polygon_coordinates: list
    num_drones: int

class KillSwitchRequest(BaseModel):
    reason: str

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

@app.get("/")
def root():
    return {"status": "ONLINE", "system": "AgroSwarm Shield Cibersecurity Node Activo"}

# 1. LOGIN
@app.post("/api/v1/auth/login")
def login(credentials: LoginRequest):
    user = USERS_DB.get(credentials.username)
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Credenciales incorrectas")
    
    token = create_access_token({"sub": user["user_id"], "rancho": user["rancho_name"]})
    return {"access_token": token, "token_type": "bearer", "rancho": user["rancho_name"]}

# 2. DESPLEGAR ENJAMBRE
@app.post("/api/v1/mission/start")
def start_mission(mission: MissionStartRequest, user: dict = Depends(get_current_user)):
    raw_command = f"DEPLOY:{mission.terreno_id}:{mission.num_drones}"
    signature = generate_mesh_signature(raw_command)
    encrypted_order = encrypt_mesh_payload(raw_command)
    
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
@app.post("/api/v1/security/kill-switch")
def trigger_kill_switch(payload: KillSwitchRequest, user: dict = Depends(get_current_user)):
    emergency_command = "KILL_SWITCH_ALL_MOTORS_OFF"
    signature = generate_mesh_signature(emergency_command)
    
    # Manejo seguro de timestamp compatible con Python 3.12+
    now_utc = datetime.now(timezone.utc).isoformat()
    
    return {
        "status": "EMERGENCY_STOP_ACTIVATED",
        "hardware_opcode": "0xFF",
        "reason": payload.reason,
        "timestamp_utc": now_utc,
        "signature_hmac": signature
    }