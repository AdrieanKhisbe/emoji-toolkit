"""Exercise the installed CLI contract against tiny, real resource bundles."""

import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest
import requests
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


def test_bundle_command_preserves_originals_and_previews(resources, tmp_path):
    output = build(resources, tmp_path)
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["schema"] == 1
    with zipfile.ZipFile(output / "apple.zip") as archive:
        assert archive.read("images/grinning_face.png") == png()
        assert (
            archive.read("images/grinning_face.url").decode()
            == "data:image/png;base64," + base64.b64encode(png()).decode()
        )
    assert not (output / "windows.zip").exists()


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


def invoke(terminal, *args):
    from emoji_dataset.cli import cli

    return terminal.invoke(cli, list(args))


def test_install_then_lookup_is_offline_and_returns_original_and_preview(
    resources, tmp_path, terminal, releases
):
    releases(build(resources, tmp_path))
    installed = invoke(terminal, "install", "--vendor", "apple")
    assert installed.exit_code == 0, installed.output
    assert installed.stdout == ""
    releases.responses.clear()
    path = invoke(terminal, ":grinning:")
    assert path.exit_code == 0, path.output
    image = Path(path.stdout.strip())
    assert image.is_absolute() and image.name == "grinning_face.png"
    assert image.read_bytes() == png()
    assert image.stat().st_mode & 0o222 == 0
    url = invoke(terminal, "grinning", "--url")
    assert (
        url.stdout.strip()
        == "data:image/png;base64," + base64.b64encode(png()).decode()
    )
    url_file = invoke(terminal, "grinning", "--url-file")
    assert Path(url_file.stdout.strip()).read_text() == url.stdout.strip()
    assert invoke(terminal, ":happy-face:").stdout == path.stdout
    assert invoke(terminal, "grinning", "--data-url").stdout == url.stdout


@pytest.mark.parametrize("command", ["get", "lookup"])
def test_explicit_lookup_after_fresh_install(
    command, resources, tmp_path, terminal, releases
):
    releases(build(resources, tmp_path))
    installed = invoke(terminal, "install", "--vendor", "apple")
    assert installed.exit_code == 0, installed.output
    releases.responses.clear()

    result = invoke(terminal, command, ":satisfied:")
    assert result.exit_code == 0, result.output
    image = Path(result.stdout.strip())
    assert image.name == "grinning_squinting_face.png"
    assert image.read_bytes() == png()
    assert result.stdout == invoke(terminal, ":satisfied:").stdout
    preview = invoke(terminal, "satisfied", "--url")
    for args in [(command, "satisfied", "--url"), (command, "--url", "satisfied")]:
        result = invoke(terminal, *args)
        assert result.exit_code == 0, result.output
        assert result.stdout == preview.stdout


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


@pytest.mark.parametrize("command", [(), ("get",), ("lookup",)])
@pytest.mark.parametrize("url_flag", ["--url", "--data-url"])
def test_sized_preview_uses_original_offline(
    command, url_flag, sized_artwork, resources, tmp_path, terminal, releases
):
    releases(build(resources, tmp_path))
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0
    releases.responses.clear()
    original = Path(invoke(terminal, "grinning").stdout.strip())
    saved_preview = original.with_suffix(".url").read_bytes()

    for args in [
        (*command, "grinning", url_flag, "--size", "128"),
        (*command, "--size", "128", url_flag, "grinning"),
    ]:
        result = invoke(terminal, *args)
        assert result.exit_code == 0, result.output
        assert result.stderr == ""
        prefix, payload = result.stdout.strip().split(",", 1)
        assert prefix == "data:image/png;base64"
        with Image.open(io.BytesIO(base64.b64decode(payload, validate=True))) as image:
            assert image.format == "PNG"
            assert image.size == (128, 64)
            assert image.getpixel((64, 32))[3] == 128
    assert original.read_bytes() == sized_artwork
    assert original.with_suffix(".url").read_bytes() == saved_preview
    assert (
        invoke(terminal, "grinning", "--url").stdout.strip().encode() == saved_preview
    )

    # A requested size is generated from the original, not the saved preview.
    original.with_suffix(".url").chmod(0o644)
    original.with_suffix(".url").unlink()
    result = invoke(terminal, *command, "grinning", url_flag, "--size", "128")
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize(
    "size,dimensions,warn", [(1, (1, 1), False), (1024, (160, 80), True)]
)
def test_preview_size_bounds_and_no_upscaling(
    size, dimensions, warn, sized_artwork, resources, tmp_path, terminal, releases
):
    releases(build(resources, tmp_path))
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0
    result = invoke(terminal, "grinning", "--url", "--size", str(size))
    assert result.exit_code == 0, result.output
    with Image.open(
        io.BytesIO(base64.b64decode(result.stdout.split(",", 1)[1]))
    ) as image:
        assert image.size == dimensions
    assert bool(result.stderr) == warn
    if warn:
        assert "160×80" in result.stderr and "1024" in result.stderr


@pytest.mark.parametrize(
    "args,message",
    [
        (("--url", "--size", "0"), "1<=x<=1024"),
        (("--url", "--size", "1025"), "1<=x<=1024"),
        (("--url", "--size", "1.5"), "integer"),
        (("--size", "128"), "requires --url"),
        (("--url-file", "--size", "128"), "--url-file"),
    ],
)
def test_invalid_preview_size_options_fail_before_lookup(terminal, args, message):
    result = invoke(terminal, "grinning", *args)
    assert result.exit_code == 2
    assert result.stdout == ""
    assert message in result.stderr


def test_preferences_tones_listing_and_reserved_words(
    resources, tmp_path, terminal, releases, monkeypatch
):
    releases(build(resources, tmp_path))
    assert (
        invoke(terminal, "install", "--vendor", "google", "--vendor", "apple").exit_code
        == 0
    )
    assert Path(invoke(terminal, "wave").stdout.strip()).parent.name == "google"
    assert invoke(terminal, "config", "set", "vendor", "apple").exit_code == 0
    assert Path(invoke(terminal, "wave").stdout.strip()).parent.name == "apple"
    monkeypatch.setenv("EMOJI_VENDOR", "google")
    assert Path(invoke(terminal, "wave").stdout.strip()).parent.name == "google"
    assert (
        Path(invoke(terminal, "wave", "--vendor", "apple").stdout.strip()).parent.name
        == "apple"
    )
    assert invoke(terminal, "config", "set", "skin-tone", "dark").exit_code == 0
    assert "waving_hand_dark_skin_tone.png" in invoke(terminal, "wave").stdout
    assert (
        "waving_hand.png" in invoke(terminal, "dark_wave", "--skin-tone", "none").stdout
    )
    assert (
        "grinning_face.png"
        in invoke(terminal, "grinning", "--skin-tone", "dark").stdout
    )
    assert invoke(terminal, "wave", "--skin-tone", "purple").exit_code != 0
    assert invoke(terminal, "config", "set", "vendor", "windows").exit_code != 0
    assert invoke(terminal, "config", "unset", "vendor").exit_code == 0
    assert "google" in invoke(terminal, "config", "show").stdout
    assert "google" in invoke(terminal, "status").stdout
    assert "resources-v1" in invoke(terminal, "status").stdout
    listed = invoke(terminal, "list", "GRINNING")
    assert listed.stdout.splitlines() == [
        "grinning",
        "happy_face",
        "install",
        "laughing",
        "satisfied",
    ]
    assert invoke(terminal, ":install:").stdout == invoke(terminal, "grinning").stdout
    for alias in ("😀", "U+1F600", "grinning face"):
        assert invoke(terminal, alias).exit_code != 0
    assert invoke(terminal, "config", "unset", "skin-tone").exit_code == 0
    assert "waving_hand.png" in invoke(terminal, "wave").stdout
    assert "waving_hand_dark_skin_tone.png" in invoke(terminal, "dark_wave").stdout


@pytest.mark.parametrize(
    "options,prefix,suffix",
    [
        ((), "", ""),
        (("--format", "plain"), "", ""),
        (("--format", "colon"), ":", ":"),
        (("--colon",), ":", ":"),
        (("--format", "emoji"), "😆 ", ""),
        (("--emoji",), "😆 ", ""),
        (("--format", "emoji", "--emoji"), "😆 ", ""),
    ],
)
def test_list_formats_preserve_aliases_and_search(
    options, prefix, suffix, resources, tmp_path, terminal, releases
):
    releases(build(resources, tmp_path))
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0
    releases.responses.clear()
    result = invoke(terminal, "list", "SQUINTING", *options)
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        prefix + alias + suffix for alias in ("laughing", "satisfied")
    ]
    assert invoke(terminal, "list", "no_such_emoji", *options).stdout == ""


def test_emoji_list_preserves_tone_and_joined_sequences(
    resources, tmp_path, terminal, releases
):
    dataset, aliases = resources
    entries = json.loads((dataset / "dataset.json").read_text())
    entries.append(
        {
            "unicode": ["U+1F469", "U+200D", "U+1F4BB"],
            "name": "woman technologist",
            "cldr_name": "woman technologist",
        }
    )
    (dataset / "dataset.json").write_text(json.dumps(entries))
    mappings = json.loads(aliases.read_text())
    mappings.append({"emoji": "👩‍💻", "aliases": ["woman_technologist"]})
    aliases.write_text(json.dumps(mappings))
    records_path = dataset / "vendors/apple.json"
    records = json.loads(records_path.read_text())
    records.append(
        {
            **records[0],
            "unicode": entries[-1]["unicode"],
            "image_path": str(dataset / "images/apple/woman technologist.png"),
        }
    )
    (dataset / "images/apple/woman technologist.png").write_bytes(png())
    records_path.write_text(json.dumps(records))
    releases(build(resources, tmp_path))
    assert (
        invoke(terminal, "install", "--vendor", "apple", "--vendor", "google").exit_code
        == 0
    )
    assert (
        invoke(terminal, "list", "wave", "--emoji").stdout == "👋🏿 dark_wave\n👋 wave\n"
    )
    assert (
        invoke(terminal, "list", "technologist", "--emoji").stdout
        == "👩‍💻 woman_technologist\n"
    )
    assert (
        invoke(terminal, "list", "technologist", "--emoji", "--vendor", "google").stdout
        == ""
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_emoji_list_preserves_presentation_selectors(
    legacy, resources, tmp_path, terminal, releases
):
    dataset, aliases = resources
    examples = {
        "copyright": "©️",
        "left_right_arrow": "↔️",
        "keycap_hash": "#️⃣",
        "keycap_asterisk": "*️⃣",
        "woman_health_worker": "👩‍⚕️",
        "rainbow_flag": "🏳️‍🌈",
        "point_up": "☝️",
        "point_up_dark": "☝🏿",
    }
    entries = json.loads((dataset / "dataset.json").read_text())
    mappings = json.loads(aliases.read_text())
    records_path = dataset / "vendors/apple.json"
    records = json.loads(records_path.read_text())
    for alias, emoji in examples.items():
        points = [f"U+{ord(character):X}" for character in emoji]
        entries.append({"unicode": points, "name": alias, "cldr_name": alias})
        mappings.append({"emoji": emoji, "aliases": [alias]})
        image = dataset / "images/apple" / f"{alias}.png"
        image.write_bytes(png())
        records.append({**records[0], "unicode": points, "image_path": str(image)})
    (dataset / "dataset.json").write_text(json.dumps(entries))
    aliases.write_text(json.dumps(mappings))
    records_path.write_text(json.dumps(records))
    folder = build(resources, tmp_path)
    if legacy:
        index_path = folder / "index.json"
        index = json.loads(index_path.read_text())
        for entry in index["entries"].values():
            entry.pop("emoji", None)
        index_path.write_text(json.dumps(index))
        manifest_path = folder / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["index"]["sha256"] = hashlib.sha256(
            index_path.read_bytes()
        ).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
    releases(folder)
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0
    releases.responses.clear()
    lines = invoke(terminal, "list", "--emoji").stdout.splitlines()
    for alias, emoji in examples.items():
        assert f"{emoji} {alias}" in lines


@pytest.mark.parametrize(
    "options",
    [
        ("--emoji", "--colon"),
        ("--format", "plain", "--emoji"),
        ("--format", "emoji", "--colon"),
        ("--format", "unknown"),
    ],
)
def test_list_rejects_invalid_or_conflicting_formats(terminal, options):
    result = invoke(terminal, "list", *options)
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "format" in result.stderr


def test_update_preserves_paths_and_other_vendors_release_aliases(
    resources, tmp_path, terminal, releases
):
    releases(build(resources, tmp_path))
    assert (
        invoke(terminal, "install", "--vendor", "apple", "--vendor", "google").exit_code
        == 0
    )
    original = invoke(terminal, "grinning").stdout
    dataset, aliases = resources
    entries = json.loads((dataset / "dataset.json").read_text())
    entries[0]["name"] = entries[0]["cldr_name"] = "renamed face"
    (dataset / "dataset.json").write_text(json.dumps(entries))
    apple = dataset / "vendors/apple.json"
    records = json.loads(apple.read_text())
    renamed = dataset / "images/apple/renamed face.png"
    renamed.write_bytes(png("green"))
    records[0]["image_path"] = str(renamed)
    records[0]["source"]["sha256"] = hashlib.sha256(png("green")).hexdigest()
    apple.write_text(json.dumps(records))
    mappings = json.loads(aliases.read_text())
    mappings[0]["aliases"] = ["smile_new"]
    aliases.write_text(json.dumps(mappings))
    releases(build(resources, tmp_path, "resources-v2"))
    noop = invoke(terminal, "install", "--vendor", "apple", "--release", "resources-v2")
    assert noop.exit_code == 0 and "already installed" in noop.stderr
    assert invoke(terminal, "grinning").stdout == original
    updated = invoke(terminal, "install", "--vendor", "apple", "--update")
    assert updated.exit_code == 0, updated.output
    assert invoke(terminal, "smile_new").stdout == original
    assert Path(original.strip()).read_bytes() == png("green")
    assert invoke(terminal, "grinning").exit_code != 0
    assert invoke(terminal, "grinning", "--vendor", "google").exit_code == 0
    assert invoke(terminal, "smile_new", "--vendor", "google").exit_code != 0
    assert "resources-v1" in invoke(terminal, "status").stdout
    assert invoke(terminal, "install", "--update").exit_code == 0
    assert "resources-v1" not in invoke(terminal, "status").stdout


@pytest.mark.parametrize("corruption", ["gif", "checksum", "preview"])
def test_builder_rejects_invalid_artwork_without_publishing(
    resources, tmp_path, corruption
):
    from emoji_dataset.bundles import cli

    dataset, aliases = resources
    path = dataset / "vendors/apple.json"
    records = json.loads(path.read_text())
    if corruption == "gif":
        Image.new("RGB", (2, 2)).save(records[0]["image_path"], format="GIF")
    elif corruption == "checksum":
        records[0]["source"]["sha256"] = "0" * 64
    else:
        records[0]["data_uri"] = "data:image/png;base64,bm90IGEgcG5n"
    path.write_text(json.dumps(records))
    output = tmp_path / "invalid"
    result = CliRunner().invoke(
        cli,
        [
            "--dataset",
            str(dataset),
            "--aliases",
            str(aliases),
            "--output",
            str(output),
            "--release",
            "bad",
            "--vendor",
            "apple",
        ],
    )
    assert result.exit_code != 0
    assert "Error:" in result.stderr
    assert not output.exists()


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


@pytest.mark.parametrize(
    "corruption",
    ["gif", "png-crc", "checksum", "unsafe", "identity", "schema", "preview"],
)
def test_invalid_update_preserves_previous_vendor_and_continues_batch(
    resources, tmp_path, terminal, releases, corruption
):
    releases(build(resources, tmp_path))
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0
    original = invoke(terminal, "grinning").stdout
    next_release = build(resources, tmp_path, "resources-v2")
    tamper_bundle(next_release, corruption)
    releases(next_release)
    update = invoke(
        terminal, "install", "--update", "--vendor", "apple", "--vendor", "google"
    )
    assert update.exit_code != 0 and "apple" in update.stderr
    assert invoke(terminal, "grinning").stdout == original
    assert Path(original.strip()).read_bytes() == png()
    status = invoke(terminal, "status").stdout
    assert "apple: resources-v1 (default)" in status
    assert "google: resources-v2" in status


@pytest.mark.parametrize("failure", ["timeout", "interrupted", 429, 503])
def test_install_retries_transient_downloads(
    resources, tmp_path, terminal, releases, monkeypatch, failure
):
    import time

    waits = []
    monkeypatch.setattr(time, "sleep", waits.append)
    folder = build(resources, tmp_path)
    releases(folder)
    url = next(url for url in releases.responses if url.endswith("/apple.zip"))
    success = releases.responses[url]
    if failure == "timeout":
        error = requests.Timeout("slow network")
    elif failure == "interrupted":
        error = requests.exceptions.ChunkedEncodingError(
            "Connection broken: IncompleteRead"
        )
    else:
        error = requests.Response()
        error.status_code = failure
        error.headers["Retry-After"] = "2"
    releases.responses[url] = [error, error, success]
    result = invoke(terminal, "install", "--vendor", "apple")
    assert result.exit_code == 0, result.output
    assert len(waits) == 2
    assert all(1 <= delay <= 3 for delay in waits)
    assert invoke(terminal, "grinning").exit_code == 0


@pytest.mark.parametrize(
    "status, retry_after, attempts",
    [(404, None, 1), (429, "61", 1), (503, None, 3), ("interrupted", None, 3)],
)
def test_install_stops_after_permanent_error_long_wait_or_retry_budget(
    resources, tmp_path, terminal, releases, monkeypatch, status, retry_after, attempts
):
    import time

    monkeypatch.setattr(time, "sleep", lambda _: None)
    releases(build(resources, tmp_path))
    url = next(url for url in releases.responses if url.endswith("/apple.zip"))
    error = requests.Response()
    error.status_code = status
    if retry_after:
        error.headers["Retry-After"] = retry_after
    if status == "interrupted":
        error = requests.exceptions.ChunkedEncodingError(
            "Connection broken: IncompleteRead"
        )
    replies = [error] * 4
    releases.responses[url] = replies
    result = invoke(terminal, "install", "--vendor", "apple")
    assert result.exit_code != 0 and "Error:" in result.stderr
    assert len(replies) == 4 - attempts
    assert invoke(terminal, "grinning").exit_code != 0


def test_latest_compatible_release_and_explicit_pin(
    resources, tmp_path, terminal, releases
):
    old = build(resources, tmp_path)
    releases(old)
    newer = build(resources, tmp_path, "resources-v2")
    manifest = json.loads((newer / "manifest.json").read_text())
    manifest["schema"] = 99
    (newer / "manifest.json").write_text(json.dumps(manifest))
    releases(newer)
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0
    assert "resources-v1" in invoke(terminal, "status").stdout
    assert (
        invoke(
            terminal, "install", "--vendor", "google", "--release", "resources-v2"
        ).exit_code
        != 0
    )
    assert (
        invoke(
            terminal, "install", "--vendor", "google", "--release", "resources-v1"
        ).exit_code
        == 0
    )
    releases.releases[-1]["immutable"] = False
    assert (
        invoke(
            terminal,
            "install",
            "--vendor",
            "google",
            "--update",
            "--release",
            "resources-v1",
        ).exit_code
        != 0
    )


def test_install_selection_and_first_success_default(
    resources, tmp_path, terminal, releases, monkeypatch
):
    import sys
    from emoji_dataset.cli import cli

    assert invoke(terminal, "install").exit_code != 0
    assert invoke(terminal, "install", "--update").exit_code != 0
    releases(build(resources, tmp_path))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    # CliRunner replaces stdin; use its stream's TTY contract at the system boundary.
    from click.testing import _NamedTextIOWrapper

    monkeypatch.setattr(_NamedTextIOWrapper, "isatty", lambda self: True)
    result = terminal.invoke(cli, ["install"], input="google,apple\n")
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "google: resources-v1 (default)" in invoke(terminal, "status").stdout


@pytest.mark.parametrize("local", [False, True])
@pytest.mark.parametrize("use_default", [False, True])
def test_install_can_explicitly_select_default(
    local, use_default, resources, tmp_path, terminal, releases
):
    releases(build(resources, tmp_path))
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0
    assert invoke(terminal, "config", "set", "skin-tone", "dark").exit_code == 0
    args = ["install", "--vendor", "google"]
    if local:
        args += ["--local-override", str(resources[0]), "--aliases", str(resources[1])]
        releases.responses.clear()
    if use_default:
        args += ["--use-as-default"]
    result = invoke(terminal, *args)
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    preferences = invoke(terminal, "config", "show").stdout
    assert f"vendor: {'google' if use_default else 'apple'}" in preferences
    assert "skin-tone: dark" in preferences
    assert Path(invoke(terminal, "wave").stdout.strip()).parent.name == (
        "google" if use_default else "apple"
    )


def test_select_existing_default_without_downloading_or_updating(
    resources, tmp_path, terminal, releases
):
    from emoji_dataset.store import Store

    releases(build(resources, tmp_path))
    assert (
        invoke(terminal, "install", "--vendor", "apple", "--vendor", "google").exit_code
        == 0
    )
    before = Store().installed()
    releases.responses.clear()
    result = invoke(terminal, "install", "--vendor", "google", "--use-as-default")
    assert result.exit_code == 0, result.output
    assert "already installed" in result.stderr
    assert result.stdout == ""
    assert "vendor: google" in invoke(terminal, "config", "show").stdout
    assert Store().installed() == before


def test_first_install_and_successful_update_can_set_default(
    resources, tmp_path, terminal, releases
):
    releases(build(resources, tmp_path))
    result = invoke(terminal, "install", "--vendor", "apple", "--use-as-default")
    assert result.exit_code == 0, result.output
    assert "vendor: apple" in invoke(terminal, "config", "show").stdout
    assert (
        invoke(terminal, "install", "--vendor", "google", "--use-as-default").exit_code
        == 0
    )
    releases(build(resources, tmp_path, "resources-v2"))
    result = invoke(
        terminal, "install", "--vendor", "apple", "--update", "--use-as-default"
    )
    assert result.exit_code == 0, result.output
    assert "vendor: apple" in invoke(terminal, "config", "show").stdout
    assert "apple: resources-v2 (default)" in invoke(terminal, "status").stdout


@pytest.mark.parametrize("answer,exit_code", [("google", 0), ("google,apple", 2)])
def test_interactive_install_default_requires_single_selection(
    answer, exit_code, resources, tmp_path, terminal, releases, monkeypatch
):
    from click.testing import _NamedTextIOWrapper
    from emoji_dataset.cli import cli

    releases(build(resources, tmp_path))
    monkeypatch.setattr(_NamedTextIOWrapper, "isatty", lambda self: True)
    result = terminal.invoke(cli, ["install", "--use-as-default"], input=answer + "\n")
    assert result.exit_code == exit_code, result.output
    if exit_code == 0:
        assert "vendor: google" in invoke(terminal, "config", "show").stdout
    else:
        assert "exactly one vendor" in result.stderr
        assert "No vendors installed" in invoke(terminal, "status").stderr


@pytest.mark.parametrize("update", [False, True])
def test_failed_install_does_not_change_requested_default(
    update, resources, tmp_path, terminal, releases
):
    from emoji_dataset.store import Store

    releases(build(resources, tmp_path))
    vendors = ["--vendor", "google"]
    if update:
        vendors += ["--vendor", "apple"]
    assert invoke(terminal, "install", *vendors).exit_code == 0
    assert invoke(terminal, "config", "set", "vendor", "google").exit_code == 0
    before = Store().config.read_bytes()
    next_release = build(resources, tmp_path, "resources-v2")
    tamper_bundle(next_release, "png-crc")
    releases(next_release)
    args = ["install", "--vendor", "apple", "--use-as-default"]
    if update:
        args += ["--update"]
    result = invoke(terminal, *args)
    assert result.exit_code != 0 and "apple" in result.stderr
    assert Store().config.read_bytes() == before
    assert "vendor: google" in invoke(terminal, "config", "show").stdout


@pytest.mark.parametrize(
    "selection",
    [("--all",), ("--vendor", "apple", "--vendor", "google"), ("--update",)],
)
def test_default_install_rejects_multiple_selected_vendors(
    selection, resources, tmp_path, terminal, releases
):
    from emoji_dataset.store import Store

    releases(build(resources, tmp_path))
    assert (
        invoke(terminal, "install", "--vendor", "apple", "--vendor", "google").exit_code
        == 0
    )
    before = Store().installed()
    releases.responses.clear()
    result = invoke(terminal, "install", *selection, "--use-as-default")
    assert result.exit_code == 2, result.output
    assert "exactly one vendor" in result.stderr
    assert result.stdout == ""
    assert Store().installed() == before
    assert "vendor: apple" in invoke(terminal, "config", "show").stdout


@pytest.mark.parametrize(
    "system,vendor", [("Darwin", "apple"), ("Windows", "windows"), ("Linux", "google")]
)
def test_setup_selects_os_vendor(
    system, vendor, resources, tmp_path, terminal, releases, monkeypatch
):
    import platform
    import shutil

    dataset, _ = resources
    shutil.copytree(dataset / "images/apple", dataset / "images/windows")
    records = json.loads((dataset / "vendors/apple.json").read_text())
    for record in records:
        record["source"]["vendor"] = "windows"
        record["image_path"] = str(
            dataset / "images/windows" / Path(record["image_path"]).name
        )
    (dataset / "vendors/windows.json").write_text(json.dumps(records))
    releases(build(resources, tmp_path, vendors=("apple", "google", "windows")))
    monkeypatch.setattr(platform, "system", lambda: system)
    result = invoke(terminal, "setup", "--yes")
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert f"{vendor}: resources-v1 (default)" in invoke(terminal, "status").stdout


@pytest.mark.parametrize("answer,success", [("y", True), ("n", False)])
def test_setup_confirms_before_download(
    answer, success, resources, tmp_path, terminal, releases, monkeypatch
):
    import platform
    from click.testing import _NamedTextIOWrapper
    from emoji_dataset.cli import cli

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(_NamedTextIOWrapper, "isatty", lambda self: True)
    if success:
        releases(build(resources, tmp_path))
    result = terminal.invoke(cli, ["setup"], input=answer + "\n")
    assert (result.exit_code == 0) == success, result.output
    assert "apple" in result.stderr
    assert result.stdout == ""
    if not success:
        assert "No vendors installed" in invoke(terminal, "status").stderr


def test_setup_requires_yes_when_unattended(terminal, monkeypatch):
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    result = invoke(terminal, "setup")
    assert result.exit_code != 0
    assert "--yes" in result.stderr and result.stdout == ""


@pytest.mark.parametrize("answer,success", [("google", True), ("google,apple", False)])
def test_unknown_os_setup_uses_single_vendor_picker(
    answer, success, resources, tmp_path, terminal, releases, monkeypatch
):
    import platform
    from click.testing import _NamedTextIOWrapper
    from emoji_dataset.cli import cli

    monkeypatch.setattr(platform, "system", lambda: "Unknown")
    for args in [("setup",), ("setup", "--yes")]:
        result = invoke(terminal, *args)
        assert result.exit_code != 0 and "emoji install --vendor" in result.stderr
    releases(build(resources, tmp_path))
    monkeypatch.setattr(_NamedTextIOWrapper, "isatty", lambda self: True)
    result = terminal.invoke(cli, ["setup", "--yes"], input=answer + "\n")
    assert (result.exit_code == 0) == success, result.output
    assert result.stdout == ""
    if success:
        assert "google: resources-v1 (default)" in invoke(terminal, "status").stdout
        assert "apple:" not in invoke(terminal, "status").stdout
    else:
        assert "exactly one vendor" in result.stderr
        assert "No vendors installed" in invoke(terminal, "status").stderr


@pytest.mark.parametrize("system", ["Darwin", "Unknown"])
@pytest.mark.parametrize("default", ["apple", "google", None])
def test_setup_existing_vendor_is_noop(
    system, default, resources, tmp_path, terminal, releases, monkeypatch
):
    import platform
    from emoji_dataset.store import Store

    monkeypatch.setattr(platform, "system", lambda: system)
    releases(build(resources, tmp_path))
    assert (
        invoke(terminal, "install", "--vendor", "google", "--vendor", "apple").exit_code
        == 0
    )
    assert invoke(terminal, "config", "set", "skin-tone", "dark").exit_code == 0
    if default is None:
        assert invoke(terminal, "uninstall", "--vendor", "google").exit_code == 0
    else:
        assert invoke(terminal, "config", "set", "vendor", default).exit_code == 0
    store = Store()
    before = store.installed()
    preferences = store.config.read_bytes()
    releases.responses.clear()
    for args in [("setup",), ("setup", "--yes")]:
        result = invoke(terminal, *args)
        assert result.exit_code == 0, result.output
        assert result.stdout == ""
        expected = (
            "apple is already installed" if system == "Darwin" else "Already set up"
        )
        assert expected in result.stderr
        assert store.installed() == before
        assert store.config.read_bytes() == preferences


@pytest.mark.parametrize("yes", [False, True])
def test_setup_rejects_other_installed_vendor(
    yes, resources, tmp_path, terminal, releases, monkeypatch
):
    import platform
    from emoji_dataset.store import Store

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    releases(build(resources, tmp_path))
    assert invoke(terminal, "install", "--vendor", "google").exit_code == 0
    store = Store()
    before = store.installed()
    preferences = store.config.read_bytes() if store.config.exists() else None
    releases.responses.clear()
    result = invoke(terminal, "setup", *(["--yes"] if yes else []))
    assert result.exit_code != 0, result.output
    assert "emoji install --vendor apple --use-as-default" in result.stderr
    assert result.stdout == ""
    assert store.installed() == before
    assert (store.config.read_bytes() if store.config.exists() else None) == preferences


def test_setup_sets_default_preserving_other_preferences(
    resources, tmp_path, terminal, releases, monkeypatch
):
    import platform
    from emoji_dataset.store import Store, atomic_json

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    atomic_json(Store().config, {"vendor": None, "skin-tone": "dark"})
    releases(build(resources, tmp_path))
    result = invoke(terminal, "setup", "--yes")
    assert result.exit_code == 0, result.output
    preferences = invoke(terminal, "config", "show").stdout
    assert "vendor: apple" in preferences
    assert "skin-tone: dark" in preferences


def test_failed_setup_preserves_preferences(
    resources, tmp_path, terminal, releases, monkeypatch
):
    import platform
    from emoji_dataset.store import Store, atomic_json

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    store = Store()
    atomic_json(store.config, {"vendor": None, "skin-tone": "dark"})
    before = store.config.read_bytes()
    folder = build(resources, tmp_path)
    tamper_bundle(folder, "png-crc")
    releases(folder)
    result = invoke(terminal, "setup", "--yes")
    assert result.exit_code != 0 and "apple" in result.stderr
    assert store.config.read_bytes() == before
    assert store.installed() == {}


@pytest.mark.parametrize("vendors", [("google",), ("google", "apple")])
def test_update_only_installed_vendors(
    vendors, resources, tmp_path, terminal, releases
):
    from emoji_dataset.store import Store

    releases(build(resources, tmp_path))
    selection = [argument for vendor in vendors for argument in ("--vendor", vendor)]
    assert invoke(terminal, "install", *selection).exit_code == 0
    releases(build(resources, tmp_path, "resources-v2", vendors=vendors))
    result = invoke(terminal, "install", "--update")
    assert result.exit_code == 0, result.output
    assert set(Store().installed()) == set(vendors)
    assert all(
        record["release"] == "resources-v2" for record in Store().installed().values()
    )
    assert "google: resources-v2 (default)" in invoke(terminal, "status").stdout


def test_update_without_installed_vendors_gives_setup_instructions(terminal):
    result = invoke(terminal, "install", "--update")
    assert result.exit_code != 0, result.output
    assert "No vendors installed" in result.stderr
    assert "emoji setup or emoji install --vendor VENDOR" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("options", [("--update", "--all"), ("--all", "--update")])
def test_install_rejects_update_all(terminal, options):
    result = invoke(terminal, "install", *options)
    assert result.exit_code == 2
    assert "Use --update without --all" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    "options", [("--vendor", "apple", "--all"), ("--all", "--vendor", "apple")]
)
def test_install_rejects_all_with_vendor(terminal, options):
    result = invoke(terminal, "install", *options)
    assert result.exit_code == 2
    assert "Choose --all or --vendor" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    "option",
    [
        "--update",
        "--use-as-default",
        "--vendor",
        "--all",
        "--local-override",
        "--local-overidde",
        "--aliases",
        "--release",
    ],
)
def test_setup_rejects_install_options(terminal, option):
    result = invoke(terminal, "setup", option)
    assert result.exit_code == 2 and "No such option" in result.stderr
    assert option not in invoke(terminal, "setup", "--help").stdout


def test_uninstall_nondefault_preserves_other_vendor_and_shared_index(
    resources, tmp_path, terminal, releases
):
    from emoji_dataset.store import Store

    releases(build(resources, tmp_path))
    assert (
        invoke(terminal, "install", "--vendor", "apple", "--vendor", "google").exit_code
        == 0
    )
    assert invoke(terminal, "config", "set", "vendor", "apple").exit_code == 0
    assert invoke(terminal, "config", "set", "skin-tone", "dark").exit_code == 0
    store = Store()
    original = Path(invoke(terminal, "grinning").stdout.strip())
    before = original.read_bytes()
    preferences = store.config.read_bytes()
    index = store.data / "indexes" / (store.installed()["apple"]["index"] + ".json")
    shared = index.read_bytes()
    releases.responses.clear()
    result = invoke(terminal, "uninstall", "--vendor", "google")
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "google" in result.stderr
    assert not (store.data / "vendors/google").exists()
    assert original.read_bytes() == before
    assert store.config.read_bytes() == preferences
    assert index.read_bytes() == shared
    assert invoke(terminal, "grinning").stdout.strip() == str(original)


@pytest.mark.parametrize("explicit", [False, True])
def test_uninstall_default_requires_new_selection(
    explicit, resources, tmp_path, terminal, releases
):
    releases(build(resources, tmp_path))
    assert (
        invoke(terminal, "install", "--vendor", "apple", "--vendor", "google").exit_code
        == 0
    )
    removed, remaining = ("google", "apple") if explicit else ("apple", "google")
    if explicit:
        assert invoke(terminal, "config", "set", "vendor", removed).exit_code == 0
    assert invoke(terminal, "config", "set", "skin-tone", "dark").exit_code == 0
    result = invoke(terminal, "uninstall", "--vendor", removed)
    assert result.exit_code == 0, result.output
    assert "emoji config set vendor" in result.stderr
    preferences = invoke(terminal, "config", "show").stdout
    assert "vendor: (unset)" in preferences and "skin-tone: dark" in preferences
    assert "(default)" not in invoke(terminal, "status").stdout
    lookup = invoke(terminal, "wave")
    assert lookup.exit_code != 0 and lookup.stdout == ""
    assert "emoji config set vendor" in lookup.stderr
    assert invoke(terminal, "wave", "--vendor", remaining).exit_code == 0
    assert invoke(terminal, "config", "set", "vendor", remaining).exit_code == 0
    assert invoke(terminal, "wave").exit_code == 0


def test_uninstall_multiple_vendors_and_absent_vendor_are_offline_noops(
    resources, tmp_path, terminal, releases
):
    from emoji_dataset.store import Store

    releases(build(resources, tmp_path))
    assert (
        invoke(terminal, "install", "--vendor", "apple", "--vendor", "google").exit_code
        == 0
    )
    releases.responses.clear()
    result = invoke(
        terminal,
        "uninstall",
        "--vendor",
        "apple",
        "--vendor",
        "google",
        "--vendor",
        "apple",
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    store = Store()
    assert store.installed() == {}
    assert not list((store.data / "indexes").glob("*.json"))
    before = store.config.read_bytes()
    result = invoke(terminal, "uninstall", "--vendor", "apple")
    assert result.exit_code == 0, result.output
    assert store.config.read_bytes() == before


@pytest.mark.parametrize("args", [(), ("--all",), ("--vendor", "unknown")])
def test_uninstall_requires_explicit_vendor(terminal, args):
    result = invoke(terminal, "uninstall", *args)
    assert result.exit_code == 2 and result.stdout == ""


def test_uninstall_config_failure_restores_artwork(
    resources, tmp_path, terminal, releases, monkeypatch
):
    import os
    from emoji_dataset.store import Store

    releases(build(resources, tmp_path))
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0
    assert invoke(terminal, "config", "set", "vendor", "apple").exit_code == 0
    image = Path(invoke(terminal, "grinning").stdout.strip())
    store = Store()
    before = store.config.read_bytes()
    real_replace = os.replace

    def fail_config(source, destination):
        if Path(destination) == store.config:
            raise OSError("simulated config failure")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_config)
    result = invoke(terminal, "uninstall", "--vendor", "apple")
    assert result.exit_code != 0 and "simulated config failure" in result.stderr
    assert store.config.read_bytes() == before
    assert image.read_bytes() == png()
    assert invoke(terminal, "grinning").stdout.strip() == str(image)


def test_uninstall_deletes_only_unused_indexes(resources, tmp_path, terminal, releases):
    from emoji_dataset.store import Store

    releases(build(resources, tmp_path))
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0
    mappings = json.loads(resources[1].read_text())
    mappings[0]["aliases"].append("new_alias")
    resources[1].write_text(json.dumps(mappings))
    releases(build(resources, tmp_path, "resources-v2"))
    assert invoke(terminal, "install", "--vendor", "google").exit_code == 0
    store = Store()
    old_index = store.data / "indexes" / (store.installed()["apple"]["index"] + ".json")
    new_index = (
        store.data / "indexes" / (store.installed()["google"]["index"] + ".json")
    )
    assert old_index != new_index
    assert invoke(terminal, "uninstall", "--vendor", "apple").exit_code == 0
    assert not old_index.exists() and new_index.is_file()
    assert invoke(terminal, "new_alias", "--vendor", "google").exit_code == 0


def test_uninstall_failure_continues_other_vendors(
    resources, tmp_path, terminal, releases, monkeypatch
):
    import os
    from emoji_dataset.store import Store

    releases(build(resources, tmp_path))
    assert (
        invoke(terminal, "install", "--vendor", "apple", "--vendor", "google").exit_code
        == 0
    )
    store = Store()
    real_replace = os.replace

    def fail_apple(source, destination):
        if Path(source) == store.data / "vendors/apple":
            raise OSError("simulated removal failure")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_apple)
    result = invoke(terminal, "uninstall", "--vendor", "apple", "--vendor", "google")
    assert result.exit_code != 0 and "simulated removal failure" in result.stderr
    assert list(store.installed()) == ["apple"]
    assert invoke(terminal, "grinning").exit_code == 0


def test_uninstall_cleanup_failure_is_a_warning(
    resources, tmp_path, terminal, releases, monkeypatch
):
    import shutil
    from emoji_dataset.store import Store

    releases(build(resources, tmp_path))
    assert (
        invoke(terminal, "install", "--vendor", "apple", "--vendor", "google").exit_code
        == 0
    )
    real_rmtree = shutil.rmtree

    def fail_cleanup(path, *args, **kwargs):
        if Path(path).name.startswith(".google-removed-"):
            raise OSError("simulated cleanup failure")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", fail_cleanup)
    result = invoke(terminal, "uninstall", "--vendor", "google")
    assert result.exit_code == 0, result.output
    assert (
        "cleanup failed" in result.stderr
        and "simulated cleanup failure" in result.stderr
    )
    assert list(Store().installed()) == ["apple"]
    assert invoke(terminal, "grinning").exit_code == 0


def test_publication_failure_rolls_back_old_artwork(
    resources, tmp_path, terminal, releases, monkeypatch
):
    import os

    releases(build(resources, tmp_path))
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0
    before = invoke(terminal, "grinning").stdout
    releases(build(resources, tmp_path, "resources-v2"))
    real_replace = os.replace

    def failed_replace(source, destination):
        if Path(source).name == "next" and Path(destination).name == "apple":
            raise OSError("simulated disk failure")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", failed_replace)
    result = invoke(terminal, "install", "--update")
    assert result.exit_code != 0
    assert invoke(terminal, "grinning").stdout == before
    assert Path(before.strip()).read_bytes() == png()
    assert "apple: resources-v1" in invoke(terminal, "status").stdout


def test_latest_search_continues_past_a_page_of_unrelated_releases(
    resources, tmp_path, terminal, releases, monkeypatch
):
    releases(build(resources, tmp_path))
    original_get = requests.Session.get

    def paged_get(session, url, **kwargs):
        if "/releases?" in url and url.endswith("page=1"):
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps(
                [
                    {"tag_name": f"program-{i}", "immutable": True, "assets": []}
                    for i in range(100)
                ]
            ).encode()
            return response
        return original_get(session, url.replace("page=2", "page=1"), **kwargs)

    monkeypatch.setattr(requests.Session, "get", paged_get)
    result = invoke(terminal, "install", "--vendor", "apple")
    assert result.exit_code == 0, result.output


def test_skin_tones_handle_hair_names_and_expanded_handshake_sequences(
    resources, tmp_path, terminal, releases
):
    dataset, aliases = resources
    extra = [
        ("1f471", "person: blond hair", "blond"),
        ("1f471-1f3ff", "person: dark skin tone, blond hair", "dark_blond"),
        ("1f91d", "handshake", "handshake"),
        ("1faf1-1f3ff-200d-1faf2-1f3ff", "handshake: dark skin tone", "dark_handshake"),
    ]
    entries = json.loads((dataset / "dataset.json").read_text())
    records = json.loads((dataset / "vendors/apple.json").read_text())
    names = json.loads(aliases.read_text())
    for key, name, alias in extra:
        points = ["U+" + part.upper() for part in key.split("-")]
        entries.append({"unicode": points, "name": alias, "cldr_name": name})
        path = dataset / "images/apple" / f"{alias}.png"
        path.write_bytes(png())
        records.append(
            {
                "unicode": points,
                "image_path": str(path),
                "data_uri": records[0]["data_uri"],
            }
        )
        names.append(
            {
                "emoji": "".join(chr(int(part, 16)) for part in key.split("-")),
                "aliases": [alias],
            }
        )
    (dataset / "dataset.json").write_text(json.dumps(entries))
    (dataset / "vendors/apple.json").write_text(json.dumps(records))
    aliases.write_text(json.dumps(names))
    releases(build(resources, tmp_path, vendors=("apple",)))
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0
    assert (
        invoke(terminal, "blond", "--skin-tone", "dark").stdout
        == invoke(terminal, "dark_blond").stdout
    )
    assert (
        invoke(terminal, "dark_blond", "--skin-tone", "none").stdout
        == invoke(terminal, "blond").stdout
    )
    assert (
        invoke(terminal, "handshake", "--skin-tone", "dark").stdout
        == invoke(terminal, "dark_handshake").stdout
    )


def test_missing_vendor_artwork_never_falls_back(
    resources, tmp_path, terminal, releases
):
    dataset, _ = resources
    path = dataset / "vendors/google.json"
    path.write_text(json.dumps(json.loads(path.read_text())[1:]))
    releases(build(resources, tmp_path))
    assert (
        invoke(terminal, "install", "--vendor", "apple", "--vendor", "google").exit_code
        == 0
    )
    result = invoke(terminal, "grinning", "--vendor", "google")
    assert result.exit_code != 0 and result.stdout == "" and "google" in result.stderr
    assert invoke(terminal, "list", "happy_face", "--vendor", "google").stdout == ""


def test_corrupt_index_rejects_install_with_actionable_error(
    resources, tmp_path, terminal, releases
):
    folder = build(resources, tmp_path)
    (folder / "index.json").write_text("[]")
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["index"]["sha256"] = hashlib.sha256(b"[]").hexdigest()
    (folder / "manifest.json").write_text(json.dumps(manifest))
    releases(folder)
    result = invoke(terminal, "install", "--vendor", "apple")
    assert result.exit_code != 0 and "Error:" in result.stderr
    assert invoke(terminal, "grinning").exit_code != 0


def test_all_install_uses_apple_first_and_keeps_successes(
    resources, tmp_path, terminal, releases
):
    releases(build(resources, tmp_path))
    result = invoke(terminal, "install", "--all")
    assert result.exit_code != 0  # The fixture intentionally provides only two vendors.
    status = invoke(terminal, "status").stdout
    assert "apple: resources-v1 (default)" in status
    assert "google: resources-v1" in status
    releases.responses.clear()
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0


def test_first_failed_vendor_does_not_become_default(
    resources, tmp_path, terminal, releases
):
    folder = build(resources, tmp_path)
    tamper_bundle(folder, "checksum")
    releases(folder)
    result = invoke(terminal, "install", "--vendor", "apple", "--vendor", "google")
    assert result.exit_code != 0
    assert "google: resources-v1 (default)" in invoke(terminal, "status").stdout


def test_bare_negative_shortcode_matches_colon_form(
    resources, tmp_path, terminal, releases
):
    aliases = resources[1]
    names = json.loads(aliases.read_text())
    names[0]["aliases"].append("-1")
    aliases.write_text(json.dumps(names))
    releases(build(resources, tmp_path))
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0
    bare = invoke(terminal, "-1")
    assert bare.exit_code == 0, bare.output
    assert bare.stdout == invoke(terminal, ":-1:").stdout
    before = invoke(terminal, "--url", "-1")
    assert before.exit_code == 0, before.output
    assert before.stdout == invoke(terminal, ":-1:", "--url").stdout


def test_backup_cleanup_failure_reports_success_and_allows_later_update(
    resources, tmp_path, terminal, releases, monkeypatch
):
    import shutil

    releases(build(resources, tmp_path))
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0
    releases(build(resources, tmp_path, "resources-v2"))
    real_rmtree = shutil.rmtree

    def failed_cleanup(path, *args, **kwargs):
        if Path(path).name.startswith(".apple-obsolete-"):
            raise OSError("simulated cleanup failure")
        return real_rmtree(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(shutil, "rmtree", failed_cleanup)
        result = invoke(terminal, "install", "--update")
    assert result.exit_code == 0, result.output
    assert "cleanup" in result.stderr.lower()
    assert "apple: resources-v2" in invoke(terminal, "status").stdout
    result = invoke(terminal, "install", "--update")
    assert result.exit_code == 0, result.output


def test_offline_lookup_is_available_while_update_downloads(
    resources, tmp_path, terminal, releases, monkeypatch
):
    import os
    import subprocess
    import sys

    releases(build(resources, tmp_path))
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0
    original = invoke(terminal, "grinning").stdout
    real_get = requests.Session.get
    lookups = []

    def lookup_during_download(session, url, **kwargs):
        if url.endswith("/apple.zip"):
            result = subprocess.run(
                [sys.executable, "-m", "emoji_dataset.cli", "grinning"],
                env={
                    **os.environ,
                    "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                },
                capture_output=True,
                text=True,
                timeout=10,
            )
            lookups.append(result)
        return real_get(session, url, **kwargs)

    monkeypatch.setattr(requests.Session, "get", lookup_during_download)
    updated = invoke(terminal, "install", "--update")
    assert updated.exit_code == 0, updated.output
    assert (
        len(lookups) == 1
        and lookups[0].returncode == 0
        and lookups[0].stdout == original
    )


def test_retiring_backup_failure_rolls_back_update(
    resources, tmp_path, terminal, releases, monkeypatch
):
    import os

    releases(build(resources, tmp_path))
    assert invoke(terminal, "install", "--vendor", "apple").exit_code == 0
    releases(build(resources, tmp_path, "resources-v2"))
    real_replace = os.replace

    def failed_retirement(source, destination):
        if Path(destination).name.startswith(".apple-obsolete-"):
            raise OSError("simulated retirement failure")
        return real_replace(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", failed_retirement)
        result = invoke(terminal, "install", "--update")
    assert result.exit_code != 0
    assert "apple: resources-v1" in invoke(terminal, "status").stdout
    assert invoke(terminal, "install", "--update").exit_code == 0


def test_config_vendor_exposes_click_choices(terminal):
    help_result = invoke(terminal, "config", "set", "vendor", "--help")
    assert help_result.exit_code == 0
    for vendor in (
        "apple",
        "emojione",
        "facebook",
        "google",
        "samsung",
        "twitter",
        "windows",
    ):
        assert vendor in "".join(help_result.stdout.split())
    invalid = invoke(terminal, "config", "set", "vendor", "unknown")
    assert invalid.exit_code == 2
    assert "Invalid value" in invalid.stderr and "apple" in invalid.stderr


def test_install_directly_from_source_is_offline_with_aliases(
    resources, terminal, monkeypatch
):
    def unexpected_network(*args, **kwargs):
        pytest.fail("Local installation with aliases must not use the network")

    monkeypatch.setattr(requests.Session, "get", unexpected_network)
    dataset, aliases = resources
    result = invoke(
        terminal,
        "install",
        "--vendor",
        "apple",
        "--local-override",
        str(dataset),
        "--aliases",
        str(aliases),
    )
    assert result.exit_code == 0, result.output
    image = Path(invoke(terminal, "grinning").stdout.strip())
    assert image.read_bytes() == png()
    assert image != dataset / "images/apple/grinning face.png"
    assert "local:" in invoke(terminal, "status").stdout
    # Local updates follow the same validation and preservation rules.
    (dataset / "images/apple/grinning face.png").write_bytes(b"broken")
    result = invoke(
        terminal,
        "install",
        "--vendor",
        "apple",
        "--local-overidde",
        str(dataset),
        "--aliases",
        str(aliases),
        "--update",
    )
    assert result.exit_code != 0
    assert image.read_bytes() == png()


def test_local_source_fetches_only_pinned_aliases_when_omitted(
    resources, terminal, monkeypatch
):
    dataset, aliases = resources
    urls = []

    def get(session, url, **kwargs):
        urls.append(url)
        response = requests.Response()
        response.status_code = 200
        response._content = aliases.read_bytes()
        return response

    monkeypatch.setattr(requests.Session, "get", get)
    result = invoke(
        terminal, "install", "--vendor", "apple", "--local-override", str(dataset)
    )
    assert result.exit_code == 0, result.output
    assert urls == [
        "https://raw.githubusercontent.com/github/gemoji/fadaeaf1f1a9be82b321316a6c5502e43138b2f6/db/emoji.json"
    ]
    assert Path(invoke(terminal, "grinning").stdout.strip()).read_bytes() == png()
    assert (
        invoke(
            terminal, "install", "--local-override", str(dataset), "--release", "v1"
        ).exit_code
        == 2
    )
    assert invoke(terminal, "install", "--aliases", str(aliases)).exit_code == 2


@pytest.mark.parametrize("corruption", ["unrecognized", "png-crc"])
def test_local_source_keeps_successful_vendors_after_failure(
    resources, terminal, corruption
):
    dataset, aliases = resources
    image = corrupt_png_crc(png()) if corruption == "png-crc" else b"broken"
    (dataset / "images/apple/grinning face.png").write_bytes(image)
    result = invoke(
        terminal,
        "install",
        "--vendor",
        "apple",
        "--vendor",
        "google",
        "--local-override",
        str(dataset),
        "--aliases",
        str(aliases),
    )
    assert result.exit_code != 0
    assert "Invalid PNG artwork" in result.stderr
    assert "google:" in invoke(terminal, "status").stdout
    assert Path(invoke(terminal, "grinning").stdout.strip()).read_bytes() == png("blue")


@pytest.mark.parametrize(
    "options",
    [
        ["--url"],
        ["--data-url"],
        ["--url-file"],
        ["--vendor", "apple", "--url"],
        ["--vendor=apple", "--url"],
        ["--skin-tone", "dark", "--url"],
    ],
)
def test_lookup_options_work_before_or_after_shortcode(resources, terminal, options):
    dataset, aliases = resources
    assert (
        invoke(
            terminal,
            "install",
            "--vendor",
            "apple",
            "--local-override",
            str(dataset),
            "--aliases",
            str(aliases),
        ).exit_code
        == 0
    )
    before = invoke(terminal, *options, "wave")
    after = invoke(terminal, "wave", *options)
    assert before.exit_code == after.exit_code == 0, before.output
    assert before.stdout == after.stdout
