import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from jose import jwt, JWTError
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
from cryptography.fernet import Fernet

# Claves Secretas del Sistema AgroSwarm
SECRET_KEY = "AGROSWARM_SHIELD_SUPER_SECRET_JWT_KEY_2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Clave secreta compartida entre el Servidor y los Nodos Mesh / ESP32
HMAC_MESH_SECRET = b"AGRO_MESH_SECRET_HMAC_KEY_9981"

# Cifrado simétrico Fernet para payload del enjambre
FERNET_KEY = Fernet.generate_key()
cipher_suite = Fernet(FERNET_KEY)

# Instancia de hasher de contraseñas moderna (reemplazo sin bugs de passlib)
password_hash_context = PasswordHash((BcryptHasher(),))

# --- FUNCIONES JWT & AUTH ---
def hash_password(password: str) -> str:
    return password_hash_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

# --- PROTOCOLO DE CIBERSEGURIDAD AERO-AGRÍCOLA (HMAC & CIFRADO) ---
def generate_mesh_signature(data: str) -> str:
    """Genera la firma única que debe acompañar a cada orden del enjambre."""
    return hmac.new(HMAC_MESH_SECRET, data.encode('utf-8'), hashlib.sha256).hexdigest()

def verify_mesh_signature(data: str, signature: str) -> bool:
    """Verifica si el paquete enviado al/del dron no sufrió inyección o tampering."""
    expected_sig = generate_mesh_signature(data)
    return hmac.compare_digest(expected_sig, signature)

def encrypt_mesh_payload(payload_str: str) -> str:
    """Cifra el paquete de datos que viaja en la red de malla."""
    return cipher_suite.encrypt(payload_str.encode('utf-8')).decode('utf-8')