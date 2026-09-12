import asyncio


from app.utils.sherlock_parser import parse_sherlock_file


async def run_sherlock(username: str):

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

    return parse_sherlock_file(stdout.decode())
