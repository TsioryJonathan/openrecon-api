import asyncio
import json


async def run_sherlock(username: str):
    process = await asyncio.create_subprocess_exec(
        "sherlock",
        username,
        "--json",
        "--print-found",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise Exception(f"Sherlock error: {stderr.decode()}")
    output = stdout.decode()
    data = json.loads(output)
    results = []
    for site, info in data.items():
        if info.get("status") == "Claimed":
            results.append({"site": site, "url": info.get("url"), "status": "found"})
    return results
