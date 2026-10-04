"""Refresh the Unicode emoji index and explicitly identified vendor artwork."""

import argparse
import base64
import copy
import fcntl
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image

from emoji_sources import (
    HttpClient,
    UNICODE_URL,
    VENDORS,
    read_unicode_index,
    sequence_key,
    validate_png,
    vendor_catalog,
)

MAX_JSON_BYTES = 100_000_000


def thumbnail_data_uri(data):
    """Encode a PNG preview without changing the original artwork."""
    with Image.open(io.BytesIO(data)) as original:
        preview = original.convert("RGBA")
        preview.thumbnail((72, 72), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        preview.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def load_entries(output):
    path = output / "dataset.json"
    if not path.exists():
        return []
    entries = json.loads(path.read_text())
    if not isinstance(entries, list):
        raise ValueError("Existing dataset.json must be an array")
    keys = [sequence_key(entry["unicode"]) for entry in entries]
    if len(keys) != len(set(keys)):
        raise ValueError("Existing dataset contains duplicate Unicode sequences")
    by_key = dict(zip(keys, entries))
    for entry in entries:
        for vendor in VENDORS:
            # Legacy embedded URLs contain full-size artwork; rebuild previews.
            if f"{vendor}_emoji" in entry:
                entry[f"{vendor}_emoji"].pop("data_uri", None)
    for vendor in VENDORS:
        vendor_path = output / "vendors" / f"{vendor}.json"
        if not vendor_path.exists():
            continue
        records = json.loads(vendor_path.read_text())
        if not isinstance(records, list):
            raise ValueError(f"{vendor_path} must be an array")
        seen = set()
        for record in records:
            key = sequence_key(record["unicode"])
            if key not in by_key or key in seen or f"{vendor}_emoji" in by_key[key]:
                raise ValueError(
                    f"Unknown or duplicate Unicode sequence in {vendor_path}"
                )
            seen.add(key)
            by_key[key][f"{vendor}_emoji"] = {
                k: v for k, v in record.items() if k != "unicode"
            }
    return entries


def write_dataset(staged, entries):
    """Write a shared Unicode index and one artwork array per vendor."""
    fields = {f"{vendor}_emoji" for vendor in VENDORS}
    index = [{k: v for k, v in entry.items() if k not in fields} for entry in entries]
    files = {staged / "dataset.json": index}
    (staged / "vendors").mkdir(exist_ok=True)
    for vendor in VENDORS:
        records = []
        for entry in entries:
            artwork = entry.get(f"{vendor}_emoji")
            if artwork is None:
                continue
            if "data_uri" not in artwork:
                relative = image_path(entry, vendor, set())
                data = (staged / relative).read_bytes()
                # Some indexed legacy .png files are GIFs. Preserve their bytes
                # and render their first frame as PNG; new downloads stay PNG-only.
                artwork["data_uri"] = thumbnail_data_uri(data)
            source = artwork.setdefault(
                "source",
                {
                    "vendor": vendor,
                    "release": None,
                    "url": None,
                    "verified": False,
                },
            )
            records.append(
                {
                    "unicode": entry["unicode"],
                    "image_path": artwork["image_path"],
                    "data_uri": artwork["data_uri"],
                    "source": source,
                }
            )
        files[staged / "vendors" / f"{vendor}.json"] = records
        print(f"{vendor}: prepared {len(records)} preview records", file=sys.stderr)
    for path, records in files.items():
        path.write_text(json.dumps(records, indent=2) + "\n")
        if path.stat().st_size >= MAX_JSON_BYTES:
            raise ValueError(f"{path.name} exceeds the 100 MB JSON limit")


def repack(output, entries):
    """Rebuild previews and split the local dataset without HTTP requests."""
    with tempfile.TemporaryDirectory(
        prefix=f".{output.name}-refresh-", dir=output.parent
    ) as directory:
        staged = Path(directory) / "next"
        shutil.copytree(output, staged)
        for entry in entries:
            for vendor in VENDORS:
                if f"{vendor}_emoji" in entry:
                    entry[f"{vendor}_emoji"].pop("data_uri", None)
        write_dataset(staged, entries)
        publish(output, staged)


def merge_index(previous, index):
    old = {sequence_key(entry["unicode"]): entry for entry in previous}
    entries = []
    for entry in index:
        existing = old.pop(sequence_key(entry["unicode"]), {})
        entries.append({**existing, **entry})
    # Preserve historical records even if the latest Unicode index omits them.
    entries.extend(old.values())
    return entries


def image_path(entry, vendor, duplicate_names):
    previous = entry.get(f"{vendor}_emoji", {}).get("image_path")
    if previous:
        parts = Path(previous).parts
        if (
            len(parts) < 3
            or parts[-3:-1] != ("images", vendor)
            or parts[-1] in {".", ".."}
        ):
            raise ValueError(f"Unsafe existing image path: {previous}")
        return Path("images") / vendor / parts[-1]
    name = entry["name"]
    if name in duplicate_names:
        name += "_" + "-".join(
            point.removeprefix("U+").lower() for point in entry["unicode"]
        )
    return Path("images") / vendor / f"{name}.png"


def publish(output, staged):
    """Swap a prepared dataset, rolling back if publication fails."""
    # Keep the recovery copy outside temporary-directory cleanup, even if rollback fails.
    backup = output.with_name(f".{output.name}-previous")
    if backup.exists():
        raise OSError(
            f"Recovery copy exists at {backup}; restore or move it before retrying"
        )
    had_previous = output.exists()
    if had_previous:
        os.replace(output, backup)
    try:
        os.replace(staged, output)
    except BaseException:
        if had_previous:
            os.replace(backup, output)
        raise
    if had_previous:
        try:
            shutil.rmtree(backup)
        except OSError as error:
            print(
                f"Dataset published, but could not remove recovery copy {backup}: {error}",
                file=sys.stderr,
            )


def prepare_paths(output, staged, entries, vendor, duplicate_names):
    """Split legacy shared paths before any artwork can overwrite retained bytes."""
    destinations = {}
    paths = {}
    reserved = {image_path(entry, vendor, duplicate_names) for entry in entries}
    for entry in entries:
        relative = image_path(entry, vendor, duplicate_names)
        key = sequence_key(entry["unicode"])
        if relative in destinations:
            suffix = "-".join(f"{point:x}" for point in key)
            replacement = relative.with_name(f"{relative.stem}_{suffix}.png")
            if replacement in reserved:
                raise ValueError(f"Conflicting migration path: {replacement}")
            reserved.add(replacement)
            if (staged / relative).is_file():
                shutil.copyfile(staged / relative, staged / replacement)
            field = entry.get(f"{vendor}_emoji")
            if field is not None:
                field["image_path"] = str(output / replacement)
            relative = replacement
        destinations[relative] = key
        paths[key] = relative
    return paths


def refresh_vendor(output, entries, index_metadata, catalog, http, selected):
    candidate = copy.deepcopy(entries)
    duplicate_names = {
        name
        for name, count in Counter(entry["name"] for entry in candidate).items()
        if count > 1
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output.name}-refresh-", dir=output.parent
    ) as directory:
        staged = Path(directory) / "next"
        if output.exists():
            shutil.copytree(output, staged)
        else:
            staged.mkdir()
        paths = prepare_paths(
            output, staged, candidate, catalog.vendor, duplicate_names
        )
        for entry in candidate:
            key = sequence_key(entry["unicode"])
            if selected and key not in selected:
                continue
            url = catalog.images.get(key)
            if url is None:
                field = f"{catalog.vendor}_emoji"
                relative = paths[key]
                if field not in entry and (staged / relative).is_file():
                    retained = (staged / relative).read_bytes()
                    try:
                        validate_png(retained)
                    except ValueError:
                        # Preserve the file, but do not advertise a legacy GIF as PNG.
                        continue
                    entry[field] = {
                        "image_path": str(output / relative),
                        "data_uri": thumbnail_data_uri(retained),
                    }
                continue
            relative = paths[key]
            data = http.png(url)
            destination = staged / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            entry[f"{catalog.vendor}_emoji"] = {
                "image_path": str(output / relative),
                "data_uri": thumbnail_data_uri(data),
                "source": {
                    "vendor": catalog.vendor,
                    "release": catalog.release,
                    "url": url,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                },
            }
        write_dataset(staged, candidate)
        (staged / "unicode-source.json").write_text(
            json.dumps(index_metadata, indent=2) + "\n"
        )
        publish(output, staged)
    return candidate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("resources/dataset"))
    parser.add_argument(
        "--vendor",
        action="append",
        choices=VENDORS,
        help="Refresh only this vendor; repeat to select several",
    )
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/emoji-dataset"))
    parser.add_argument(
        "--request-delay",
        type=float,
        default=0.25,
        help="Minimum seconds between requests to the same host",
    )
    parser.add_argument(
        "--emoji",
        action="append",
        help="Refresh only this Unicode sequence, e.g. U+1F600 or U+1F44B-U+1F3FB",
    )
    parser.add_argument(
        "--repack",
        action="store_true",
        help="Split local JSON and rebuild 72px previews without downloading",
    )
    args = parser.parse_args(argv)
    if args.request_delay < 0:
        parser.error("--request-delay must be nonnegative")
    if args.repack and (args.vendor or args.emoji):
        parser.error("--repack processes all local artwork; omit --vendor and --emoji")
    errors = []
    lock = None
    try:
        output = args.output.resolve()
        if (
            output == Path.cwd()
            or output in Path.cwd().parents
            or args.output.is_symlink()
        ):
            raise ValueError(
                "--output must be a dedicated dataset directory, not the working directory or an ancestor"
            )
        if args.cache_dir.resolve().is_relative_to(output):
            raise ValueError("--cache-dir must be outside --output")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        lock = args.output.with_name(f".{args.output.name}-refresh.lock").open("a")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backup = args.output.with_name(f".{args.output.name}-previous")
        if backup.exists():
            raise OSError(
                f"Recovery copy exists at {backup}; restore or move it before retrying"
            )
        previous = load_entries(args.output)
        if args.repack:
            if not (args.output / "dataset.json").is_file():
                raise ValueError("--repack requires an existing dataset.json")
            repack(args.output, previous)
            print("Local dataset split by vendor with 72px PNG previews")
            return 0
        selected = {
            sequence_key(value.replace("U+", "").replace("-", " ").split())
            for value in args.emoji or []
        }
        with requests.Session() as session:
            session.headers["User-Agent"] = (
                "Emoji-Dataset (https://github.com/AdrieanKhisbe/emoji-toolkit)"
            )
            http = HttpClient(session, args.cache_dir, args.request_delay)
            response = http.request("get", UNICODE_URL)
            version, index = read_unicode_index(response.content.decode("utf-8"))
            keys = {sequence_key(entry["unicode"]) for entry in index}
            if selected - keys:
                raise ValueError(
                    "--emoji contains a sequence absent from the Unicode index"
                )
            entries = merge_index(previous, index)
            metadata = {
                "url": UNICODE_URL,
                "version": version,
                "sha256": hashlib.sha256(response.content).hexdigest(),
            }
            for vendor in dict.fromkeys(args.vendor or VENDORS):
                try:
                    catalog = vendor_catalog(http, vendor)
                    updated = refresh_vendor(
                        args.output, entries, metadata, catalog, http, selected
                    )
                    entries = updated
                    print(f"{vendor}: refreshed from {catalog.release}")
                except (requests.RequestException, ValueError, OSError) as error:
                    errors.append(vendor)
                    print(f"{vendor}: unchanged: {error}", file=sys.stderr)
                    if backup.exists():
                        print(
                            f"Original dataset retained at {backup}; restore or move it before retrying",
                            file=sys.stderr,
                        )
                        break
        return 1 if errors else 0
    except (requests.RequestException, ValueError, OSError) as error:
        print(f"Regeneration failed: {error}", file=sys.stderr)
        return 1
    finally:
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    sys.exit(main())
