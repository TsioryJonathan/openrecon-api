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
        "lens": data.get("LensModel") or data.get("LensInfo"),
        "camera_settings": {
            "focal_length": data.get("FocalLength"),
            "focal_length_35mm": data.get("FocalLength35mmEquiv"),
            "f_number": data.get("FNumber"),
            "exposure_time": data.get("ExposureTime"),
            "iso": data.get("ISO"),
            "exposure_program": data.get("ExposureProgram"),
            "exposure_compensation": data.get("ExposureCompensation"),
        },
        "image": {
            "width": data.get("ExifImageWidth") or data.get("ImageWidth"),
            "height": data.get("ExifImageHeight") or data.get("ImageHeight"),
            "color_space": data.get("ColorSpace"),
            "bits_per_sample": data.get("BitsPerSample"),
        },
        "flash": str(data.get("Flash", "")) if data.get("Flash") is not None else None,
        "white_balance": str(data.get("WhiteBalance", "")) if data.get("WhiteBalance") is not None else None,
        "scene_type": str(data.get("SceneType", "")) if data.get("SceneType") is not None else None,
        "datetime": data.get("DateTimeOriginal") or data.get("CreateDate"),
        "software": data.get("Software"),
        "artist": data.get("Artist"),
        "copyright": data.get("Copyright"),
    }
