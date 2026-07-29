from cryptography.fernet import Fernet

# Generamos una clave simétrica para pruebas
KEY = Fernet.generate_key()
cipher_suite = Fernet(KEY)

def encrypt_command(command: str) -> str:
    """Cifra un comando de texto plano a bytes codificados en base64."""
    encrypted_bytes = cipher_suite.encrypt(command.encode('utf-8'))
    return encrypted_bytes.decode('utf-8')

def decrypt_command(token: str) -> str:
    """Descifra el token recibido de vuelta a texto plano."""
    decrypted_bytes = cipher_suite.decrypt(token.encode('utf-8'))
    return decrypted_bytes.decode('utf-8')