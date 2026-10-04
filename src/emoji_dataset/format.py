"""Resource format shared by bundle production and installation."""

import base64
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image

VENDORS = ("apple", "emojione", "facebook", "google", "samsung", "twitter", "windows")
TONES = ("none", "light", "medium-light", "medium", "medium-dark", "dark")
SCHEMA = 1


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def sequence(points: list[str]) -> str:
    return "-".join(
        f"{int(point.removeprefix('U+'), 16):x}"
        for point in points
        if int(point.removeprefix("U+"), 16) != 0xFE0F
    )


def shortcode(value: str) -> str:
    value = value.removeprefix(":").removesuffix(":").replace("-", "_")
    if not re.fullmatch(r"[a-z0-9_+]+", value):
        raise ValueError("Use a GitHub shortcode, for example :grinning:.")
    return value


def filename(value: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\0" in value
    ):
        raise ValueError(f"Unsafe filename: {value!r}")
    return value.replace(" ", "_")


def validate_png(data: bytes, preview: bool = False) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "PNG":
                raise ValueError("Artwork must contain genuine PNG data")
            if preview and max(image.size) > 72:
                raise ValueError("Preview must fit within 72×72 pixels")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
    except (OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise ValueError(f"Invalid PNG artwork: {error}") from error


def preview_bytes(url: str) -> bytes:
    prefix = "data:image/png;base64,"
    if not url.startswith(prefix):
        raise ValueError("Preview must be a PNG data URL")
    data = base64.b64decode(url[len(prefix) :], validate=True)
    validate_png(data, preview=True)
    return data


def read_json(path: Path) -> Any:
    return json.loads(path.read_bytes())


def validate_index(index: dict[str, Any]) -> None:
    if not isinstance(index, dict) or index.get("schema") != SCHEMA:
        raise ValueError("Incompatible resource index schema")
    entries, aliases = index["entries"], index["aliases"]
    if (
        not isinstance(entries, dict)
        or not isinstance(aliases, dict)
        or not entries
        or not aliases
    ):
        raise ValueError("Resource index must contain emojis and shortcodes")
    for alias, key in aliases.items():
        if shortcode(alias) != alias or key not in entries:
            raise ValueError("Invalid shortcode mapping in resource index")
    for key, entry in entries.items():
        if not isinstance(entry, dict):
            raise ValueError("Invalid emoji entry in index")
        if not re.fullmatch(r"[0-9a-f]+(?:-[0-9a-f]+)*", key):
            raise ValueError("Invalid Unicode key in index")
        if (
            not isinstance(entry["name"], str)
            or not isinstance(entry["cldr_name"], str)
            or entry["base"] not in entries
        ):
            raise ValueError("Invalid emoji entry in resource index")
        for tone, target in entry.get("tones", {}).items():
            if tone not in TONES or target not in entries:
                raise ValueError("Invalid skin-tone mapping in index")
