"""Build resource releases independently from the small CLI package."""

import re
import tempfile
import os
import zipfile
from pathlib import Path
from typing import Any

import click

from .format import (
    SCHEMA,
    TONES,
    VENDORS,
    digest,
    encode_json,
    filename,
    read_json,
    sequence,
    shortcode,
    validate_png,
    preview_bytes,
)


def build_index(dataset: Path, aliases: Path) -> dict[str, Any]:
    entries = {}
    for entry in read_json(dataset / "dataset.json"):
        key = sequence(entry["unicode"])
        if key in entries:
            raise ValueError(f"Duplicate Unicode sequence: {key}")
        entries[key] = {
            "name": entry["name"],
            "cldr_name": entry.get("cldr_name", entry["name"]),
        }
    names = {}
    for key, entry in entries.items():
        if not any(0x1F3FB <= int(point, 16) <= 0x1F3FF for point in key.split("-")):
            names[entry["cldr_name"]] = key
    for key, entry in entries.items():
        name = re.sub(
            r"(?:: |, )(?:light|medium-light|medium|medium-dark|dark) skin tone",
            "",
            entry["cldr_name"],
        )
        untoned = "-".join(
            p for p in key.split("-") if not 0x1F3FB <= int(p, 16) <= 0x1F3FF
        )
        if name in {"kiss: person, person", "couple with heart: person, person"}:
            name = name.split(":", 1)[0]
        base = untoned if untoned in entries else names.get(name, key)
        entry["base"] = base
        entries[base].setdefault("tones", {})["none"] = base
        tones = {
            int(p, 16) - 0x1F3FA
            for p in key.split("-")
            if 0x1F3FB <= int(p, 16) <= 0x1F3FF
        }
        if len(tones) == 1:
            entries[base]["tones"][TONES[tones.pop()]] = key
    shortcodes: dict[str, str] = {}
    for record in read_json(aliases):
        key = sequence([f"U+{ord(c):X}" for c in record["emoji"]])
        if key not in entries:
            continue
        for alias in record["aliases"]:
            alias = shortcode(alias)
            if alias in shortcodes and shortcodes[alias] != key:
                raise ValueError(f"Conflicting shortcode: {alias}")
            shortcodes[alias] = key
    if not shortcodes:
        raise ValueError("No GitHub shortcodes match the Unicode index")
    return {"schema": SCHEMA, "entries": entries, "aliases": shortcodes}


def build_vendor(
    dataset: Path, vendor: str, output: Path, index: dict[str, Any]
) -> None:
    records = {}
    used = set()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for record in read_json(dataset / "vendors" / f"{vendor}.json"):
            key = sequence(record["unicode"])
            if key not in index["entries"] or key in records:
                raise ValueError(f"Unknown or duplicate sequence in {vendor}: {key}")
            original = Path(record["image_path"]).name
            name = filename(original)
            if name in used:
                name = f"{Path(name).stem}_{key}.png"
            if name in used:
                raise ValueError(f"Conflicting filename: {name}")
            used.add(name)
            image = (dataset / "images" / vendor / original).read_bytes()
            validate_png(image)
            source = record.get("source", {})
            if source.get("sha256") and source["sha256"] != digest(image):
                raise ValueError(f"Original checksum mismatch: {vendor}/{original}")
            preview_bytes(record["data_uri"])
            url = record["data_uri"].encode()
            archive.writestr(f"images/{name}", image)
            archive.writestr(f"images/{Path(name).stem}.url", url)
            records[key] = {
                "filename": name,
                "sha256": digest(image),
                "url_sha256": digest(url),
                "source": record.get("source", {}),
            }
        archive.writestr(
            "vendor.json",
            encode_json({"schema": SCHEMA, "vendor": vendor, "records": records}),
        )


@click.command()
@click.option(
    "--dataset",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="resources/dataset",
    show_default=True,
)
@click.option(
    "--aliases",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Pinned GitHub gemoji db/emoji.json file.",
)
@click.option("--release", required=True, help="Immutable GitHub release tag.")
@click.option("--output", required=True, type=click.Path(path_type=Path))
@click.option(
    "--vendor",
    multiple=True,
    type=click.Choice(VENDORS),
    help="Repeat to select vendors; default: all seven.",
)
def cli(
    dataset: Path, aliases: Path, release: str, output: Path, vendor: tuple[str, ...]
) -> None:
    """Build validated vendor archives, a shared index, and a release manifest."""
    try:
        if output.exists():
            raise ValueError(
                "Output already exists; choose a new directory for this release"
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent) as directory:
            staged = Path(directory) / "release"
            staged.mkdir()
            index = build_index(dataset, aliases)
            index_bytes = encode_json(index)
            (staged / "index.json").write_bytes(index_bytes)
            manifest: dict[str, Any] = {
                "schema": SCHEMA,
                "release": release,
                "index": {"file": "index.json", "sha256": digest(index_bytes)},
                "aliases_sha256": digest(aliases.read_bytes()),
                "vendors": {},
            }
            for name in dict.fromkeys(vendor or VENDORS):
                path = staged / f"{name}.zip"
                build_vendor(dataset, name, path, index)
                manifest["vendors"][name] = {
                    "file": path.name,
                    "sha256": digest(path.read_bytes()),
                }
            (staged / "manifest.json").write_bytes(encode_json(manifest))
            os.replace(staged, output)
        click.echo(f"📦 Bundles ready: {output}", err=True)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise click.ClickException(str(error)) from error


if __name__ == "__main__":
    cli()
