#!/usr/bin/env python3
"""Pre-flight: verify the Python environment can actually run Aegis.

    python scripts/check_env.py            # backend + pipeline
    python scripts/check_env.py --backend  # backend only

Exit 0 = OK. Otherwise prints what is wrong and how to fix it.
"""

import sys

MIN, MAX = (3, 10), (3, 12)


def probe(label, fn):
    try:
        fn()
        return None
    except BaseException as e:      # face_recognition can call quit() -> SystemExit
        return f"{label}: {type(e).__name__}: {str(e).splitlines()[0][:160] if str(e) else ''}"


def main() -> int:
    backend_only = "--backend" in sys.argv
    problems = []

    if not (MIN <= sys.version_info[:2] <= MAX):
        problems.append(
            f"Python {sys.version_info.major}.{sys.version_info.minor} is outside the tested range "
            f"{MIN[0]}.{MIN[1]}–{MAX[0]}.{MAX[1]}"
        )

    checks = [
        ("fastapi / sqlalchemy", lambda: (__import__("fastapi"), __import__("sqlalchemy"))),
    ]
    if not backend_only:
        checks += [
            ("opencv", lambda: __import__("cv2")),
            ("torch", lambda: __import__("torch")),
            ("ultralytics", lambda: __import__("ultralytics")),
        ]
    checks.append(("face_recognition (dlib models)", lambda: __import__("face_recognition")))

    for label, fn in checks:
        err = probe(label, fn)
        if err:
            problems.append(err)

    if not problems:
        print(f"environment OK (Python {sys.version_info.major}.{sys.version_info.minor})")
        return 0

    print("Environment check FAILED:")
    for p in problems:
        print(f"  - {p}")
    print("\nFix: use the project virtualenv —\n"
          "  python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt\n"
          "(./run.sh does this automatically when .venv is missing.)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
