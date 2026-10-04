"""Resolve resource releases once and download their checksummed assets."""

import json
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterator

import requests

from .format import SCHEMA, digest

RELEASES_URL = "https://api.github.com/repos/AdrieanKhisbe/emoji-toolkit/releases"


class ReleaseClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "emoji/0.1"

    def download(self, url: str) -> bytes:
        for attempt in range(3):
            retry_after = 0.0
            try:
                response = self.session.get(url, timeout=30)
                if response.status_code != 429 and response.status_code < 500:
                    response.raise_for_status()
                    return response.content
                header = response.headers.get("Retry-After")
                if header:
                    try:
                        retry_after = float(header)
                    except ValueError:
                        try:
                            retry_after = (
                                parsedate_to_datetime(header)
                                - datetime.now(timezone.utc)
                            ).total_seconds()
                        except (ValueError, TypeError, OverflowError):
                            retry_after = 0
                if retry_after > 60:
                    raise ValueError(
                        f"Server requests a {retry_after:.0f}s wait. Wait and rerun emoji install."
                    )
                response.raise_for_status()
            except (
                requests.ConnectionError,
                requests.Timeout,
                requests.HTTPError,
                requests.exceptions.ChunkedEncodingError,
            ) as error:
                if isinstance(error, requests.HTTPError):
                    status = (
                        error.response.status_code if error.response is not None else 0
                    )
                    if status != 429 and status < 500:
                        raise
                if attempt == 2:
                    raise
                time.sleep(
                    min(60, max(retry_after, 2**attempt + random.uniform(0, 0.25)))
                )
        raise AssertionError("Unreachable retry state")

    def asset(
        self, release: dict[str, Any], name: str, checksum: str | None = None
    ) -> bytes:
        asset = next((a for a in release["assets"] if a["name"] == name), None)
        if asset is None:
            raise ValueError(f"Release has no {name}")
        data = self.download(asset["browser_download_url"])
        expected = checksum or str(asset.get("digest", "")).removeprefix("sha256:")
        if digest(data) != expected:
            raise ValueError(f"Checksum mismatch for {name}")
        return data

    def releases(self, tag: str | None) -> Iterator[dict[str, Any]]:
        from urllib.parse import quote

        if tag:
            yield json.loads(
                self.download(f"{RELEASES_URL}/tags/{quote(tag, safe='')}")
            )
            return
        page = 1
        while True:
            releases = json.loads(
                self.download(f"{RELEASES_URL}?per_page=100&page={page}")
            )
            yield from releases
            if len(releases) < 100:
                return
            page += 1

    def resolve(self, tag: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
        for release in self.releases(tag):
            if (
                release.get("draft")
                or release.get("prerelease")
                or not release.get("immutable")
            ):
                continue
            if not any(a["name"] == "manifest.json" for a in release.get("assets", [])):
                continue
            manifest = json.loads(self.asset(release, "manifest.json"))
            if (
                manifest.get("schema") == SCHEMA
                and manifest.get("release") == release["tag_name"]
            ):
                return release, manifest
        raise ValueError(
            "No compatible immutable resource release found. "
            "Ask the maintainer to publish resource bundles, or install from a local checkout: "
            "emoji install --vendor apple --local-override resources/dataset."
        )
