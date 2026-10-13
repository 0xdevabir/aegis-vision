"""Let the suite run where dlib's model files are unavailable (stub face_recognition)."""
import sys
import types

try:
    import face_recognition  # noqa: F401
except BaseException:  # ImportError, RuntimeError (dlib models), or SystemExit (quit())
    sys.modules.pop("face_recognition", None)
    sys.modules["face_recognition"] = types.ModuleType("face_recognition")
