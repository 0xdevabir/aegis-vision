"""Evidence encryption: AES-256-GCM, with read-only support for the older Fernet blobs.

Blob layout (v1): b"AEG1" | 12-byte nonce | ciphertext+tag. Anything without the
magic prefix is treated as a legacy Fernet token (AES-128-CBC + HMAC), so evidence
saved before the switch still opens. New data is always written as v1.
"""
import base64
import os
from functools import lru_cache

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import load_dotenv

load_dotenv()

MAGIC_V1 = b"AEG1"
_NONCE_LEN = 12
_INSECURE = {"", "default-key-change-in-prod", "default-salt"}


class EncryptionConfigError(RuntimeError):
    """ENCRYPTION_KEY / ENCRYPTION_SALT missing or left at a known default."""


@lru_cache(maxsize=8)
def _derive(password: bytes, salt: bytes, iterations: int) -> bytes:
    # PBKDF2 is deliberately slow; managers are built per request, so derive once per key.
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations).derive(password)


class EncryptionManager:
    def __init__(self):
        password = os.getenv("ENCRYPTION_KEY", "")
        salt = os.getenv("ENCRYPTION_SALT", "")
        if password in _INSECURE or salt in _INSECURE or "CHANGE_THIS" in (password[:11], salt[:11]):
            # No built-in fallback: a key everyone can read in the source protects nothing.
            raise EncryptionConfigError("ENCRYPTION_KEY and ENCRYPTION_SALT must be set to non-default values")
        self._password = password.encode()
        self._salt = salt.encode()

    def _aes(self) -> AESGCM:
        return AESGCM(_derive(self._password, self._salt + b"|aes-256-gcm", 600_000))

    def _legacy_fernet(self) -> Fernet:
        return Fernet(base64.urlsafe_b64encode(_derive(self._password, self._salt, 100_000)))

    def encrypt(self, data: bytes) -> bytes:
        nonce = os.urandom(_NONCE_LEN)
        return MAGIC_V1 + nonce + self._aes().encrypt(nonce, data, MAGIC_V1)

    def decrypt(self, encrypted_data: bytes) -> bytes:
        blob = bytes(encrypted_data)
        if blob.startswith(MAGIC_V1):
            nonce, body = blob[len(MAGIC_V1):len(MAGIC_V1) + _NONCE_LEN], blob[len(MAGIC_V1) + _NONCE_LEN:]
            return self._aes().decrypt(nonce, body, MAGIC_V1)
        return self._legacy_fernet().decrypt(blob)

    @staticmethod
    def is_legacy(encrypted_data: bytes) -> bool:
        return not bytes(encrypted_data[:len(MAGIC_V1)]) == MAGIC_V1

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
