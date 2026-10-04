"""Unicode identity and explicitly versioned Emojipedia artwork sources."""

import hashlib
import io
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from PIL import Image

UNICODE_URL = "https://www.unicode.org/Public/emoji/latest/emoji-test.txt"
GRAPHQL_URL = "https://emojipedia.org/api/graphql"
IMAGE_ORIGIN = "https://em-content.zobj.net/"
VENDORS = {
    "apple": "apple",
    "emojione": "joypixels",
    "facebook": "facebook",
    "google": "noto-color-emoji",
    "samsung": "samsung",
    "twitter": "twitter",
    "windows": "microsoft",
}
RELEASE_QUERY = """query VendorReleases($slug: Slug!, $lang: Language) {
  vendorHistoric_v1(slug: $slug, lang: $lang) { slug title date }
}"""
IMAGE_QUERY = """query VendorImages($slug: Slug!, $version: Slug!, $lang: Language) {
  vendorHistoricEmoji_v1(slug: $slug, version: $version, lang: $lang) {
    items { images { slug image { source } status } }
    statuses
  }
}"""


class SourceError(ValueError):
    """A source failed or no longer matches its expected format."""


def sequence_key(points):
    """Match vendor spellings that omit the emoji presentation selector."""
    return tuple(
        int(point.removeprefix("U+"), 16)
        for point in points
        if int(point.removeprefix("U+"), 16) != 0xFE0F
    )


def read_unicode_index(text):
    version = re.search(r"^# Version: (\d+\.\d+)\s*$", text, re.MULTILINE)
    if not version:
        raise SourceError("Unicode response has no emoji version header")
    entries = []
    seen = set()
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = re.fullmatch(
            r"([0-9A-F ]+)\s*;\s*([\w-]+)\s*#\s*\S+\s+E[\d.]+\s+(.+)", line
        )
        if not match:
            raise SourceError(f"Unexpected Unicode index row: {line[:100]}")
        points, status, name = match.groups()
        if status != "fully-qualified":
            continue
        points = [f"U+{point}" for point in points.split()]
        key = sequence_key(points)
        if key in seen:
            raise SourceError(f"Duplicate Unicode sequence: {points}")
        seen.add(key)
        filename_name = {
            (0x23, 0x20E3): "keycap number sign",
            (0x2A, 0x20E3): "keycap asterisk",
        }.get(key, name)
        entries.append(
            {
                "index": str(len(entries) + 1),
                "unicode": points,
                "name": re.sub(r"([^\s\w]|_)+", "", filename_name).strip(),
                "cldr_name": name,
            }
        )
    if not entries:
        raise SourceError("Unicode index contains no fully-qualified emoji")
    return version.group(1), entries


def validate_png(data):
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "PNG":
                raise SourceError("Artwork is not a PNG")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
    except (OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise SourceError(f"Invalid PNG artwork: {error}") from error


class HttpClient:
    """Rate-aware requests with a validated, resumable artwork cache."""

    def __init__(self, session, cache_dir, delay=0.25):
        self.session = session
        self.cache_dir = cache_dir
        self.delay = delay
        self.last_request = {}
        self.blocked = {}

    def request(self, method, url, **kwargs):
        host = urlparse(url).netloc
        if host in self.blocked:
            raise SourceError(self.blocked[host])
        remaining = self.delay - (time.monotonic() - self.last_request.get(host, 0))
        if remaining > 0:
            time.sleep(remaining)
        try:
            response = getattr(self.session, method)(url, timeout=(10, 60), **kwargs)
        finally:
            self.last_request[host] = time.monotonic()
        if response.status_code == 429:
            retry = response.headers.get("Retry-After", "not specified")
            message = f"{host}: HTTP 429; Retry-After: {retry}. Stop and retry later."
            self.blocked[host] = message
            raise SourceError(message)
        response.raise_for_status()
        return response

    def graphql(self, operation, query, variables):
        payload = self.request(
            "post",
            GRAPHQL_URL,
            json={
                "operationName": operation,
                "query": query,
                "variables": variables,
            },
        ).json()
        if (
            not isinstance(payload, dict)
            or payload.get("errors")
            or not isinstance(payload.get("data"), dict)
        ):
            raise SourceError(
                f"{operation}: invalid GraphQL response: {str(payload)[:300]}"
            )
        return payload["data"]

    def png(self, url):
        cache = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".png")
        if cache.is_file():
            data = cache.read_bytes()
            try:
                validate_png(data)
                return data
            except ValueError:
                cache.unlink()
        data = self.request("get", url).content
        validate_png(data)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
        return data


@dataclass
class Catalog:
    vendor: str
    release: str
    images: dict


def vendor_catalog(http, vendor):
    slug = VENDORS[vendor]
    variables = {"slug": slug, "lang": "EN"}
    releases = http.graphql("VendorReleases", RELEASE_QUERY, variables).get(
        "vendorHistoric_v1"
    )
    if not isinstance(releases, list) or not releases:
        raise SourceError(f"{vendor}: missing release history")
    try:
        released = [item for item in releases if 0 <= item["date"] <= time.time()]
        latest = max(released, key=lambda item: item["date"])
        release = latest["slug"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", release):
            raise ValueError("invalid release slug")
    except (KeyError, TypeError, ValueError) as error:
        raise SourceError(f"{vendor}: invalid release history") from error
    payload = http.graphql(
        "VendorImages", IMAGE_QUERY, {**variables, "version": release}
    )
    try:
        groups = payload["vendorHistoricEmoji_v1"]["items"]
        images = {}
        for group in groups:
            for item in group["images"]:
                if item["status"] == "REMOVED":
                    continue
                if item["status"] not in {"NEW", "CHANGED", "UNCHANGED"}:
                    raise ValueError("unknown image status")
                source = item["image"]["source"]
                if not re.fullmatch(
                    rf"source/{re.escape(slug)}/\d+/[^/]+\.png", source
                ):
                    raise ValueError(f"unexpected vendor image URL: {source}")
                # Tone filenames can repeat the modifier after the full sequence.
                candidates = re.findall(
                    r"_([0-9a-f]{2,6}(?:-[0-9a-f]{2,6})*)(?=[_.])", source
                )
                points = max(candidates, key=lambda value: len(value.split("-"))).split(
                    "-"
                )
                key = sequence_key(points)
                url = IMAGE_ORIGIN + source
                if key in images and images[key] != url:
                    raise ValueError(f"ambiguous artwork for {points}")
                images[key] = url
        if not images:
            raise ValueError("empty image catalogue")
    except (KeyError, TypeError, ValueError) as error:
        raise SourceError(f"{vendor}: invalid image catalogue: {error}") from error
    return Catalog(vendor, release, images)
