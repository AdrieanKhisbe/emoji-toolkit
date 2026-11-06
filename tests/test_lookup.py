"""Exercise lookup behavior through the CLI."""

import base64
import hashlib
import io
import json
from pathlib import Path
import pytest
from PIL import Image
from .helpers import build, invoke, png


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
