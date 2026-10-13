"""Evidence encryption: AES-256-GCM, tamper detection, legacy Fernet blobs, no default key."""
import base64

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet

from backend.utils import encryption as enc


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-encryption-key")
    monkeypatch.setenv("ENCRYPTION_SALT", "unit-test-salt")
    return enc.EncryptionManager()


def test_round_trip_and_fresh_nonce_per_message(manager):
    a, b = manager.encrypt(b"evidence"), manager.encrypt(b"evidence")
    assert a != b and a.startswith(enc.MAGIC_V1) and b"evidence" not in a
    assert manager.decrypt(a) == manager.decrypt(b) == b"evidence"
    assert not manager.is_legacy(a)


def test_tampered_blob_is_rejected(manager):
    blob = bytearray(manager.encrypt(b"evidence"))
    blob[-1] ^= 1
    with pytest.raises(InvalidTag):
        manager.decrypt(bytes(blob))


def test_wrong_key_cannot_decrypt(manager, monkeypatch):
    blob = manager.encrypt(b"evidence")
    monkeypatch.setenv("ENCRYPTION_KEY", "a-different-key")
    with pytest.raises(InvalidTag):
        enc.EncryptionManager().decrypt(blob)


def test_legacy_fernet_evidence_still_decrypts(manager):
    key = base64.urlsafe_b64encode(enc._derive(b"unit-test-encryption-key", b"unit-test-salt", 100_000))
    old = Fernet(key).encrypt(b"old evidence")
    assert manager.is_legacy(old)
    assert manager.decrypt(old) == b"old evidence"


@pytest.mark.parametrize("key,salt", [("", "s"), ("k", ""), ("default-key-change-in-prod", "s"),
                                      ("k", "default-salt"), ("CHANGE_THIS_KEY", "s"), ("k", "CHANGE_THIS_SALT")])
def test_missing_or_default_secrets_are_refused(monkeypatch, key, salt):
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    monkeypatch.setenv("ENCRYPTION_SALT", salt)
    with pytest.raises(enc.EncryptionConfigError):
        enc.EncryptionManager()


def test_encrypt_file_replaces_plaintext(manager, tmp_path):
    f = tmp_path / "shot.jpg"
    f.write_bytes(b"jpeg-bytes")
    out = manager.encrypt_file(str(f))
    assert not f.exists() and out.endswith(".enc")
    assert manager.decrypt_file(out) == b"jpeg-bytes"
