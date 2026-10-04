"""Local resources and preferences; callers only see committed installations."""

from contextlib import contextmanager
import fcntl
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import uuid
from typing import Any, Iterator
import zipfile

from .format import (
    SCHEMA,
    VENDORS,
    digest,
    encode_json,
    filename,
    read_json,
    validate_index,
    validate_png,
    preview_bytes,
)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(encode_json(value))
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Store:
    def __init__(self) -> None:
        self.data = (
            Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
            / "emojies"
        ).resolve()
        self.config = (
            Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
            / "emojies/config.json"
        ).resolve()

    @contextmanager
    def locked(self, *, exclusive: bool = True) -> Iterator[None]:
        self.data.mkdir(parents=True, exist_ok=True)
        with (self.data / ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield

    def preferences(self) -> dict[str, Any]:
        return read_json(self.config) if self.config.exists() else {}

    def installed(self) -> dict[str, Any]:
        result = {}
        for vendor in VENDORS:
            path = self.data / "vendors" / vendor / "installation.json"
            if path.exists():
                result[vendor] = read_json(path)
        return dict(sorted(result.items(), key=lambda item: item[1]["installed_at"]))

    def default_vendor(self) -> str | None:
        return self.preferences().get("vendor") or next(iter(self.installed()), None)

    def vendor(self, requested: str | None) -> str:
        vendor = requested or os.environ.get("EMOJI_VENDOR") or self.default_vendor()
        if not vendor or vendor not in self.installed():
            raise ValueError(
                f"Vendor {vendor or '(none)'} is not installed. Run emoji install --vendor {vendor or 'apple'}."
            )
        return vendor

    def collection(self, vendor: str) -> tuple[dict[str, Any], dict[str, Any]]:
        installation = self.installed()[vendor]
        index = read_json(self.data / "indexes" / f"{installation['index']}.json")
        return index, installation["records"]

    def install(
        self, vendor: str, release: str, index_bytes: bytes, bundle: bytes
    ) -> str | None:
        index = json.loads(index_bytes)
        validate_index(index)
        index_hash = digest(index_bytes)
        parent = self.data / "vendors"
        parent.mkdir(exist_ok=True)
        destination = parent / vendor
        backup = parent / f".{vendor}-previous"
        if backup.exists():
            raise ValueError(
                f"Recovery copy exists: {backup}. Restore it before retrying."
            )
        previous = self.installed().get(vendor, {})
        with tempfile.TemporaryDirectory(dir=parent, prefix=f".{vendor}-") as directory:
            staged = Path(directory) / "next"
            staged.mkdir()
            with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                metadata = json.loads(archive.read("vendor.json"))
                if not isinstance(metadata, dict) or metadata.get("schema") != SCHEMA:
                    raise ValueError("Incompatible vendor bundle schema")
                if metadata["vendor"] != vendor:
                    raise ValueError("Vendor bundle identity mismatch")
                records = metadata["records"]
                if not isinstance(records, dict) or not records:
                    raise ValueError("Empty vendor bundle")
                names = archive.namelist()
                if len(names) != len(set(names)):
                    raise ValueError("Duplicate files in vendor bundle")
                expected_files = {"vendor.json"}
                for record in records.values():
                    name = filename(record["filename"])
                    if not name.endswith(".png") or name != record["filename"]:
                        raise ValueError("Invalid PNG filename")
                    for extension in (".png", ".url"):
                        member = "images/" + str(Path(name).with_suffix(extension))
                        if member in expected_files:
                            raise ValueError("Shared image filenames in vendor bundle")
                        expected_files.add(member)
                if set(names) != expected_files:
                    raise ValueError("Unexpected or missing files in vendor bundle")
                paths = dict(previous.get("paths", {}))
                used = {name.casefold() for name in paths.values()}
                for key, record in records.items():
                    if key not in index["entries"]:
                        raise ValueError("Artwork not in release index")
                    name = filename(record["filename"])
                    installed_name = paths.get(key)
                    if installed_name is None:
                        installed_name = name
                        suffix = 0
                        while installed_name.casefold() in used:
                            suffix += 1
                            installed_name = f"{Path(name).stem}_{key}_{suffix}.png"
                        paths[key] = installed_name
                        used.add(installed_name.casefold())
                    for extension in (".png", ".url"):
                        target = str(Path(name).with_suffix(extension))
                        data = archive.read(f"images/{target}")
                        checksum = record[
                            "sha256" if extension == ".png" else "url_sha256"
                        ]
                        if digest(data) != checksum:
                            raise ValueError(f"Checksum mismatch for {target}")
                        if extension == ".png":
                            validate_png(data)
                        else:
                            preview_bytes(data.decode("utf-8"))
                        destination_name = str(
                            Path(installed_name).with_suffix(extension)
                        )
                        (staged / destination_name).write_bytes(data)
                        (staged / destination_name).chmod(0o444)
                    record["filename"] = installed_name
            atomic_json(self.data / "indexes" / f"{index_hash}.json", index)
            atomic_json(
                staged / "installation.json",
                {
                    "release": release,
                    "index": index_hash,
                    "installed_at": previous.get("installed_at", time.time_ns()),
                    "records": records,
                    "paths": paths,
                },
            )
            obsolete = parent / f".{vendor}-obsolete-{uuid.uuid4().hex}"
            if destination.exists():
                os.replace(destination, backup)
            try:
                os.replace(staged, destination)
                if backup.exists():
                    os.replace(backup, obsolete)
            except BaseException:
                if backup.exists():
                    if destination.exists():
                        os.replace(destination, staged)
                    os.replace(backup, destination)
                raise
            if obsolete.exists():
                # Publication is complete. Cleanup failure is a warning, not
                # an unsuccessful update or an interrupted-publication marker.
                try:
                    shutil.rmtree(obsolete)
                except OSError as error:
                    return f"Installed {vendor}; cleanup failed at {obsolete}: {error}"
        return None
