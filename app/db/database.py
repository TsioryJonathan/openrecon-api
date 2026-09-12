import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL is None:
    raise RuntimeError("Database URL is not set")
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=2,
    max_overflow=1,
    pool_pre_ping=True,
)


class Base(DeclarativeBase):
    pass


AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
