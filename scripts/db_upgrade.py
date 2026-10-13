#!/usr/bin/env python3
"""Bring the database schema up to date (used by the Docker entrypoint).

* Fresh database  -> create tables from the models, then stamp Alembic at head.
* Existing, never stamped (created by the app's create_all) -> stamp at head.
* Stamped database -> `alembic upgrade head`.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

from backend.db.database import engine, init_db  # noqa: E402


def main() -> None:
    cfg = Config(os.path.join(ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(ROOT, "alembic"))
    stamped = "alembic_version" in inspect(engine).get_table_names()
    init_db()                       # create_all + additive columns (idempotent)
    if stamped:
        command.upgrade(cfg, "head")
        print("schema upgraded to head")
    else:
        command.stamp(cfg, "head")
        print("schema created and stamped at head")


if __name__ == "__main__":
    main()
