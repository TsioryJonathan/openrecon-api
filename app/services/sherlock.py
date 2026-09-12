import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Result
from app.models.Search import Search
from app.utils.sherlock_parser import parse_sherlock_file


async def run_sherlock(username: str, db: AsyncSession):
    try:
        search = Search(username=username)
        db.add(search)
        await db.flush()

        process = await asyncio.create_subprocess_exec(
            "sherlock",
            username,
            "--print-found",
            "--no-color",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(f"Sherlock error: {stderr.decode()}")
        parsed = parse_sherlock_file(stdout.decode())
        for r in parsed:
            result = Result(search_id=search.id, site=r["domain"], url=r["url"])
            db.add(result)
        await db.commit()
        return parsed
    except Exception:
        await db.rollback()
        raise
