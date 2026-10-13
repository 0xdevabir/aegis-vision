from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os
from dotenv import load_dotenv

load_dotenv()


class EncryptionManager:
    def __init__(self):
        password = os.getenv("ENCRYPTION_KEY", "default-key-change-in-prod").encode()
        salt = os.getenv("ENCRYPTION_SALT", "default-salt").encode()
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
        key = base64.urlsafe_b64encode(kdf.derive(password))
        self.fernet = Fernet(key)

    def encrypt(self, data: bytes) -> bytes:
        return self.fernet.encrypt(data)

    def decrypt(self, encrypted_data: bytes) -> bytes:
        return self.fernet.decrypt(encrypted_data)

    def encrypt_file(self, file_path: str) -> str:
        with open(file_path, "rb") as f:
            data = f.read()
        encrypted = self.encrypt(data)
        enc_path = file_path + ".enc"
        with open(enc_path, "wb") as f:
            f.write(encrypted)
        os.remove(file_path)
        return enc_path

    def decrypt_file(self, encrypted_path: str) -> bytes:
        with open(encrypted_path, "rb") as f:
            data = f.read()
        return self.decrypt(data)
