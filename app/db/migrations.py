import asyncio
import os
from pathlib import Path

from alembic.config import Config as AlembicConfig

from alembic import command as alembic_command

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


async def run_migrations():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")

    config = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", db_url)
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))

    await asyncio.to_thread(alembic_command.upgrade, config, "head")
