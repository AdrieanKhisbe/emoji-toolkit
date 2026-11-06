"""Shared CLI fixtures using temporary resources and simulated releases."""

import base64
import hashlib
import json
from pathlib import Path
import pytest
import requests
from click.testing import CliRunner
from PIL import Image
from .helpers import png


@pytest.fixture
def resources(tmp_path):
    dataset = tmp_path / "dataset"
    (dataset / "vendors").mkdir(parents=True)
    entries = [
        {"unicode": ["U+1F600"], "name": "grinning face", "cldr_name": "grinning face"},
        {
            "unicode": ["U+1F606"],
            "name": "grinning squinting face",
            "cldr_name": "grinning squinting face",
        },
        {"unicode": ["U+1F44B"], "name": "waving hand", "cldr_name": "waving hand"},
        {
            "unicode": ["U+1F44B", "U+1F3FF"],
            "name": "waving hand dark skin tone",
            "cldr_name": "waving hand: dark skin tone",
        },
    ]
    (dataset / "dataset.json").write_text(json.dumps(entries))
    for vendor, color in [("apple", "red"), ("google", "blue")]:
        folder = dataset / "images" / vendor
        folder.mkdir(parents=True)
        records = []
        for entry in entries:
            image = folder / (entry["name"] + ".png")
            image.write_bytes(png(color))
            records.append(
                {
                    "unicode": entry["unicode"],
                    "image_path": str(image),
                    "data_uri": "data:image/png;base64,"
                    + base64.b64encode(png(color)).decode(),
                    "source": {
                        "vendor": vendor,
                        "sha256": hashlib.sha256(png(color)).hexdigest(),
                    },
                }
            )
        (dataset / "vendors" / f"{vendor}.json").write_text(json.dumps(records))
    aliases = tmp_path / "aliases.json"
    aliases.write_text(
        json.dumps(
            [
                {"emoji": "😀", "aliases": ["grinning", "happy_face", "install"]},
                {"emoji": "😆", "aliases": ["laughing", "satisfied"]},
                {"emoji": "👋", "aliases": ["wave"]},
                {"emoji": "👋🏿", "aliases": ["dark_wave"]},
            ]
        )
    )
    return dataset, aliases


@pytest.fixture
def terminal(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("EMOJI_VENDOR", raising=False)
    return CliRunner()


@pytest.fixture
def releases(monkeypatch):
    releases = []
    responses = {}

    def publish(folder):
        assets = []
        for path in folder.iterdir():
            url = f"https://github.com/AdrieanKhisbe/emoji-toolkit/releases/download/{folder.name}/{path.name}"
            data = path.read_bytes()
            responses[url] = data
            assets.append(
                {
                    "name": path.name,
                    "browser_download_url": url,
                    "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                }
            )
        releases.insert(
            0,
            {
                "tag_name": folder.name,
                "immutable": True,
                "draft": False,
                "prerelease": False,
                "assets": assets,
            },
        )

    def get(session, url, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response.url = url
        if url.endswith("/releases?per_page=100&page=1"):
            value = json.dumps(releases).encode()
        elif "/releases/tags/" in url:
            matches = [r for r in releases if r["tag_name"] == url.rsplit("/", 1)[1]]
            value = json.dumps(matches[0] if matches else {}).encode()
            if not matches:
                response.status_code = 404
        else:
            value = responses[url]
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, requests.Response):
            return value
        response._content = value
        return response

    monkeypatch.setattr(requests.Session, "get", get)
    publish.responses = responses
    publish.releases = releases
    return publish


@pytest.fixture
def sized_artwork(resources):
    dataset, _ = resources
    records_path = dataset / "vendors/apple.json"
    records = json.loads(records_path.read_text())
    original = Path(records[0]["image_path"])
    Image.new("RGBA", (160, 80), (100, 20, 40, 128)).save(original)
    records[0]["source"]["sha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
    records_path.write_text(json.dumps(records))
    return original.read_bytes()
