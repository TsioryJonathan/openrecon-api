import asyncio
import json


def _normalize_gps(data: dict) -> dict | None:
    lat = data.get("GPSLatitude")
    lon = data.get("GPSLongitude")
    if lat is None or lon is None:
        return None
    lat_ref = data.get("GPSLatitudeRef", "N")
    lon_ref = data.get("GPSLongitudeRef", "E")
    if lat_ref not in ("N", "S"):
        lat_ref = "N"
    if lon_ref not in ("E", "W"):
        lon_ref = "E"
    return {
        "lat": float(lat) if lat_ref == "N" else -float(lat),
        "lon": float(lon) if lon_ref == "E" else -float(lon),
        "altitude": data.get("GPSAltitude"),
    }


async def run_exif_extract(filepath: str) -> dict:
    process = await asyncio.create_subprocess_exec(
        "exiftool",
        "-json",
        "-n",
        filepath,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise RuntimeError(stderr.decode().strip() or "exiftool failed")

    try:
        data = json.loads(stdout.decode())[0]
    except (IndexError, json.JSONDecodeError):
        return {}

    return {
        "has_gps": data.get("GPSLatitude") is not None,
        "gps": _normalize_gps(data),
        "device": {
            "make": data.get("Make"),
            "model": data.get("Model"),
        },
        "datetime": data.get("DateTimeOriginal") or data.get("CreateDate"),
        "software": data.get("Software"),
        "artist": data.get("Artist"),
        "copyright": data.get("Copyright"),
    }
