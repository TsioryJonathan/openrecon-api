import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Result
from app.models.Search import Search
from app.utils.sherlock_parser import parse_sherlock_file

SITES = [
    "Twitter", "Instagram", "Facebook", "TikTok", "Snapchat",
    "Pinterest", "Tumblr", "Reddit", "YouTube", "WhatsApp",
    "GitHub", "GitLab", "HackerNews", "DevTo", "StackOverflow",
    "CodePen", "BitBucket",
    "Behance", "Dribbble", "DeviantArt", "Flickr", "500px",
    "Unsplash", "SoundCloud",
    "Steam", "Twitch", "Roblox", "XboxLive", "PlayStationNetwork",
    "LinkedIn", "AngelList", "Keybase",
    "Spotify", "Bandcamp", "LastFM",
    "Ethereum", "BitcoinForum",
    "Medium", "WordPress", "Substack", "Quora", "Gravatar", "About.me",
    "Etsy", "Patreon", "Kickstarter", "Fiverr", "Upwork",
    "ProductHunt", "Archive.org",
]


async def run_sherlock(username: str, db: AsyncSession):
    try:
        search = Search(username=username)

        db.add(search)
        await db.commit()
        await db.refresh(search)

        process = await asyncio.create_subprocess_exec(
            "sherlock",
            username,
            "--print-found",
            "--no-color",
            "--timeout", "10",
            *[arg for site in SITES for arg in ("--site", site)],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(f"Sherlock error: {stderr.decode()}")

        parsed = parse_sherlock_file(stdout.decode())

        for r in parsed:
            result = Result(
                search_id=search.id,
                site=r["site"],
                url=r["url"],
            )
            db.add(result)

        await db.commit()

        return parsed

    except Exception:
        await db.rollback()
        raise


async def get_results_by_username(
    username: str,
    db: AsyncSession,
):
    stmt = (
        select(Search)
        .where(Search.username == username)
        .options(selectinload(Search.results))
    )

    result = await db.execute(stmt)
    searches = result.scalars().all()

    if not searches:
        return {"message": "Search does not exist yet"}

    return searches
