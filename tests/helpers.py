"""Small image, bundle, and CLI helpers shared by the test suites."""

import hashlib
import io
import json
import zipfile
from click.testing import CliRunner
from PIL import Image


def png(color="red"):
    output = io.BytesIO()
    Image.new("RGBA", (2, 2), color).save(output, format="PNG")
    return output.getvalue()


def corrupt_png_crc(data):
    corrupted = bytearray(data)
    chunk = corrupted.index(b"IDAT")
    length = int.from_bytes(corrupted[chunk - 4 : chunk], "big")
    corrupted[chunk + 4 + length] ^= 1
    return bytes(corrupted)


def build(resources, tmp_path, release="resources-v1", vendors=("apple", "google")):
    from emoji_dataset.bundles import cli

    output = tmp_path / release
    args = [
        "--dataset",
        str(resources[0]),
        "--aliases",
        str(resources[1]),
        "--release",
        release,
        "--output",
        str(output),
    ]
    for vendor in vendors:
        args += ["--vendor", vendor]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    return output


def invoke(terminal, *args):
    from emoji_dataset.cli import cli

    return terminal.invoke(cli, list(args))


def tamper_bundle(folder, corruption):
    path = folder / "apple.zip"
    with zipfile.ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    if corruption in {"gif", "png-crc"}:
        stream = io.BytesIO()
        Image.new("RGB", (2, 2)).save(stream, format="GIF")
        image = stream.getvalue() if corruption == "gif" else corrupt_png_crc(png())
        files["images/grinning_face.png"] = image
        metadata = json.loads(files["vendor.json"])
        metadata["records"]["1f600"]["sha256"] = hashlib.sha256(image).hexdigest()
        files["vendor.json"] = json.dumps(metadata).encode()
    elif corruption == "checksum":
        files["images/grinning_face.png"] = png("black")
    elif corruption == "unsafe":
        metadata = json.loads(files["vendor.json"])
        metadata["records"]["1f600"]["filename"] = "../../escaped.png"
        files["vendor.json"] = json.dumps(metadata).encode()
    elif corruption == "identity":
        metadata = json.loads(files["vendor.json"])
        metadata["vendor"] = "google"
        files["vendor.json"] = json.dumps(metadata).encode()
    elif corruption == "schema":
        metadata = json.loads(files["vendor.json"])
        metadata["schema"] = 99
        files["vendor.json"] = json.dumps(metadata).encode()
    elif corruption == "preview":
        files["images/grinning_face.url"] = b"data:image/png;base64,bm90IGEgcG5n"
        metadata = json.loads(files["vendor.json"])
        metadata["records"]["1f600"]["url_sha256"] = hashlib.sha256(
            files["images/grinning_face.url"]
        ).hexdigest()
        files["vendor.json"] = json.dumps(metadata).encode()
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["vendors"]["apple"]["sha256"] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    (folder / "manifest.json").write_text(json.dumps(manifest))
