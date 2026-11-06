"""Exercise config behavior through the CLI."""

import json
from pathlib import Path
from .helpers import build, invoke, png


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
