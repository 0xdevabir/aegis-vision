"""Let the suite run where dlib's model files are unavailable (stub face_recognition)."""
import os
import sys
import types

# Test-only secrets, so a bare `pytest` works without a .env (CI sets its own).
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-32chars")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-32-chars!!")
os.environ.setdefault("ENCRYPTION_SALT", "test-salt-value")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key-for-ci")

try:
    import face_recognition  # noqa: F401
except BaseException:  # ImportError, RuntimeError (dlib models), or SystemExit (quit())
    sys.modules.pop("face_recognition", None)
    sys.modules["face_recognition"] = types.ModuleType("face_recognition")
