import base64
import hashlib
import io
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
from PIL import Image
from graphql import parse

import generate_emoji_dataset

UNICODE = """# emoji-test.txt
# Version: 17.0
1F600 ; fully-qualified # 😀 E1.0 grinning face
1F44B 1F3FB ; fully-qualified # 👋🏻 E1.0 waving hand: light skin tone
263A ; unqualified # ☺ E0.6 smiling face
"""


def png(color):
    output = io.BytesIO()
    Image.new("RGBA", (2, 2), color).save(output, format="PNG")
    return output.getvalue()


def response(content, status=200, headers=None):
    result = requests.Response()
    result.status_code = status
    result._content = (
        content if isinstance(content, bytes) else json.dumps(content).encode()
    )
    result.headers.update(headers or {})
    return result


class Sources:
    def __init__(self):
        self.unicode = UNICODE
        self.images = {}
        self.catalogs = {}
        self.releases = {}

    def vendor(self, slug, color, version="v1", date=1):
        source = f"source/{slug}/123/grinning-face_1f600.png"
        self.images[f"https://em-content.zobj.net/{source}"] = png(color)
        self.releases[slug] = [{"slug": version, "title": version, "date": date}]
        self.catalogs[slug] = {
            "items": [
                {
                    "images": [
                        {
                            "slug": "grinning-face",
                            "image": {"source": source},
                            "status": "CHANGED",
                        }
                    ]
                }
            ],
            "statuses": ["CHANGED"],
        }
        return self.images[f"https://em-content.zobj.net/{source}"]

    def get(self, url, **kwargs):
        if url == generate_emoji_dataset.UNICODE_URL:
            return response(self.unicode.encode())
        item = self.images[url]
        return item if isinstance(item, requests.Response) else response(item)

    def post(self, url, *, json, **kwargs):
        assert url == "https://emojipedia.org/api/graphql"
        parse(json["query"])
        slug = json["variables"]["slug"]
        if json["operationName"] == "VendorReleases":
            return response({"data": {"vendorHistoric_v1": self.releases[slug]}})
        return response({"data": {"vendorHistoricEmoji_v1": self.catalogs[slug]}})


def run(output, sources, *vendors):
    args = [
        "--output",
        str(output),
        "--cache-dir",
        str(output.parent / "cache"),
        "--request-delay",
        "0",
    ]
    for vendor in vendors:
        args.extend(["--vendor", vendor])
    with (
        patch.object(requests.Session, "get", side_effect=sources.get),
        patch.object(requests.Session, "post", side_effect=sources.post),
    ):
        return generate_emoji_dataset.main(args)


@pytest.fixture
def output(tmp_path):
    return tmp_path / "resources" / "dataset"


@pytest.fixture
def sources():
    return Sources()


def test_repack_preserves_indexed_legacy_gif_and_encodes_png_preview(output):
    image = output / "images/windows/legacy.png"
    image.parent.mkdir(parents=True)
    Image.new("RGBA", (12, 12), "red").save(image, format="GIF")
    original = image.read_bytes()
    (output / "dataset.json").write_text(
        json.dumps(
            [
                {
                    "unicode": ["U+2194", "U+FE0F"],
                    "name": "legacy",
                    "windows_emoji": {"image_path": str(image)},
                }
            ]
        )
    )
    assert generate_emoji_dataset.main(["--output", str(output), "--repack"]) == 0
    assert image.read_bytes() == original
    record = json.loads((output / "vendors/windows.json").read_text())[0]
    data = base64.b64decode(record["data_uri"].split(",", 1)[1])
    with Image.open(io.BytesIO(data)) as preview:
        assert preview.format == "PNG"
        assert preview.size == (12, 12)


def test_repack_splits_index_and_keeps_originals_with_rgba_previews(output, sources):
    image = output / "images/apple/example.png"
    image.parent.mkdir(parents=True)
    original = Image.new("RGBA", (160, 80), (0, 0, 0, 0))
    original.paste((250, 123, 45, 255), (40, 20, 120, 60))
    original.save(image)
    original_bytes = image.read_bytes()
    index = [
        {"unicode": ["U+1F600"], "name": "example"},
        {"unicode": ["U+1F44B", "U+1F3FB"], "name": "no artwork"},
    ]
    legacy = [dict(entry) for entry in index]
    legacy[0]["apple_emoji"] = {
        "image_path": str(image),
        "data_uri": "old",
        "source": {"vendor": "apple"},
    }
    (output / "dataset.json").write_text(json.dumps(legacy))
    archive = output / "dataset-big.json"
    archive.write_bytes(b"archive must stay identical")
    with (
        patch.object(requests.Session, "get") as get,
        patch.object(requests.Session, "post") as post,
    ):
        assert generate_emoji_dataset.main(["--output", str(output), "--repack"]) == 0
        get.assert_not_called()
        post.assert_not_called()
    assert json.loads((output / "dataset.json").read_text()) == index
    records = json.loads((output / "vendors/apple.json").read_text())
    assert len(records) == 1
    assert set(records[0]) == {"unicode", "image_path", "data_uri", "source"}
    assert records[0]["source"] == {"vendor": "apple"}
    assert records[0]["unicode"] == index[0]["unicode"]
    assert records[0]["image_path"] == str(image)
    assert json.loads((output / "vendors/google.json").read_text()) == []
    with Image.open(
        io.BytesIO(base64.b64decode(records[0]["data_uri"].split(",", 1)[1]))
    ) as preview:
        assert preview.size == (72, 36)
        assert preview.mode == "RGBA"
        assert preview.getpixel((0, 0))[3] == 0
    assert image.read_bytes() == original_bytes
    assert archive.read_bytes() == b"archive must stay identical"
    # The new layout is accepted on a later refresh; other vendors survive.
    sources.vendor("noto-color-emoji", "blue")
    apple_bytes = (output / "vendors/apple.json").read_bytes()
    assert run(output, sources, "google") == 0
    assert (output / "vendors/apple.json").read_bytes() == apple_bytes
    assert image.read_bytes() == original_bytes


def test_oversized_vendor_json_aborts_publication(output, sources):
    sources.vendor("apple", "red")
    gradient = io.BytesIO()
    Image.linear_gradient("L").convert("RGBA").save(gradient, format="PNG")
    sources.images[next(iter(sources.images))] = gradient.getvalue()
    output.mkdir(parents=True)
    (output / "dataset.json").write_text("[]\n")
    with patch.object(generate_emoji_dataset, "MAX_JSON_BYTES", 350):
        assert run(output, sources, "apple") == 1
    assert (output / "dataset.json").read_text() == "[]\n"
    assert list(output.iterdir()) == [output / "dataset.json"]


def test_legacy_shared_path_is_split_without_overwriting_retained_artwork(
    output, sources
):
    sources.vendor("apple", "red")
    sources.unicode = "# Version: 17.0\n0023 FE0F 20E3 ; fully-qualified # #️⃣ E0.6 keycap: #\n002A FE0F 20E3 ; fully-qualified # *️⃣ E2.0 keycap: *\n"
    source = "source/apple/123/keycap_23-fe0f-20e3.png"
    sources.catalogs["apple"]["items"] = [
        {
            "images": [
                {
                    "slug": "keycap-number-sign",
                    "image": {"source": source},
                    "status": "CHANGED",
                }
            ]
        }
    ]
    sources.images[f"https://em-content.zobj.net/{source}"] = png("red")
    shared = output / "images/apple/keycap.png"
    shared.parent.mkdir(parents=True)
    shared.write_bytes(png("green"))
    (output / "dataset.json").write_text(
        json.dumps(
            [
                {
                    "unicode": [f"U+{code}", "U+FE0F", "U+20E3"],
                    "name": "keycap",
                    "apple_emoji": {"image_path": str(shared)},
                }
                for code in ["0023", "002A"]
            ]
        )
    )
    assert run(output, sources, "apple") == 0
    entries = generate_emoji_dataset.load_entries(output)
    paths = [Path(entry["apple_emoji"]["image_path"]) for entry in entries]
    assert paths[0] == shared
    assert paths[0] != paths[1]
    assert paths[0].read_bytes() == png("red")
    assert paths[1].read_bytes() == png("green")


def test_cache_inside_output_is_rejected_before_network_or_changes(output):
    with patch.object(requests.Session, "get") as get:
        status = generate_emoji_dataset.main(
            ["--output", str(output), "--cache-dir", str(output / "cache")]
        )
    assert status == 1
    get.assert_not_called()
    assert not output.exists()


def test_rate_limited_catalog_stops_other_requests_to_same_host(
    output, sources, capsys
):
    with (
        patch.object(requests.Session, "get", side_effect=sources.get),
        patch.object(
            requests.Session,
            "post",
            return_value=response(b"limited", 429, {"Retry-After": "60"}),
        ) as post,
    ):
        status = generate_emoji_dataset.main(
            ["--output", str(output), "--request-delay", "0"]
        )
    assert status == 1
    assert post.call_count == 1
    assert "Retry-After: 60" in capsys.readouterr().err
    assert not output.exists()


def test_failed_publication_restores_original(output, sources):
    sources.vendor("apple", "red")
    output.mkdir(parents=True)
    (output / "dataset.json").write_text("[]\n")
    replace = os.replace

    def fail_staging(source, destination):
        if Path(source).name == "next":
            raise OSError("simulated publication failure")
        return replace(source, destination)

    with patch.object(os, "replace", side_effect=fail_staging):
        assert run(output, sources, "apple") == 1
    assert (output / "dataset.json").read_text() == "[]\n"
    assert list(output.iterdir()) == [output / "dataset.json"]


def test_failed_publication_and_rollback_keep_recoverable_original(
    output, sources, tmp_path
):
    sources.vendor("apple", "red")
    output.mkdir(parents=True)
    (output / "dataset.json").write_text("[]\n")
    replace = os.replace

    def fail_after_backup(source, destination):
        if Path(destination) == output:
            raise OSError("simulated filesystem failure")
        return replace(source, destination)

    with patch.object(os, "replace", side_effect=fail_after_backup):
        assert run(output, sources, "apple") == 1
    copies = list(tmp_path.rglob("dataset.json"))
    assert len(copies) == 1
    assert copies[0].read_text() == "[]\n"


def test_vendor_mismatch_rejects_catalog_without_changes(output, sources):
    sources.vendor("apple", "red")
    sources.catalogs["apple"]["items"][0]["images"][0]["image"][
        "source"
    ] = "source/google/123/grinning-face_1f600.png"
    assert run(output, sources, "apple") == 1
    assert not output.exists()


def test_all_seven_local_vendor_identifiers_select_expected_sources(output, sources):
    mapping = {
        "apple": "apple",
        "emojione": "joypixels",
        "facebook": "facebook",
        "google": "noto-color-emoji",
        "samsung": "samsung",
        "twitter": "twitter",
        "windows": "microsoft",
    }
    expected = {}
    for (vendor, slug), color in zip(
        mapping.items(), ["red", "blue", "green", "yellow", "purple", "black", "white"]
    ):
        expected[vendor] = sources.vendor(slug, color)
    assert run(output, sources) == 0
    entry = generate_emoji_dataset.load_entries(output)[0]
    for vendor, slug in mapping.items():
        record = entry[f"{vendor}_emoji"]
        assert Path(record["image_path"]).read_bytes() == expected[vendor]
        assert record["source"]["vendor"] == vendor
        assert record["source"]["release"] == "v1"
        assert (
            record["source"]["sha256"] == hashlib.sha256(expected[vendor]).hexdigest()
        )
        assert "retrieved_at" in record["source"]


def test_late_invalid_download_rolls_back_vendor_and_keeps_other_vendor_progress(
    output, sources
):
    sources.vendor("apple", "red")
    google = sources.vendor("noto-color-emoji", "blue")
    source = "source/apple/123/waving-hand_light-skin-tone_1f44b-1f3fb_1f3fb.png"
    sources.catalogs["apple"]["items"][0]["images"].append(
        {
            "slug": "waving-hand-light-skin-tone",
            "image": {"source": source},
            "status": "NEW",
        }
    )
    sources.images[f"https://em-content.zobj.net/{source}"] = b"GIF89a-not-a-png"
    old_path = output / "images/apple/old name.png"
    old_path.parent.mkdir(parents=True)
    old = png("green")
    old_path.write_bytes(old)
    (output / "dataset.json").write_text(
        json.dumps(
            [
                {
                    "unicode": ["U+1F600"],
                    "name": "old name",
                    "apple_emoji": {
                        "image_path": str(old_path),
                        "source": {"release": "old"},
                    },
                }
            ]
        )
    )
    assert run(output, sources, "apple", "google") == 1
    assert old_path.read_bytes() == old
    entries = generate_emoji_dataset.load_entries(output)
    assert entries[0]["apple_emoji"]["source"] == {"release": "old"}
    assert Path(entries[0]["google_emoji"]["image_path"]).read_bytes() == google
    assert list((output / "images/apple").iterdir()) == [old_path]


def test_tone_filename_maps_full_sequence_and_preserves_existing_path(output, sources):
    sources.vendor("apple", "red")
    source = "source/apple/123/waving-hand_light-skin-tone_1f44b-1f3fb_1f3fb.png"
    sources.catalogs["apple"]["items"][0]["images"].append(
        {
            "slug": "waving-hand-light-skin-tone",
            "image": {"source": source},
            "status": "NEW",
        }
    )
    expected = png("blue")
    sources.images[f"https://em-content.zobj.net/{source}"] = expected
    old = output / "images/apple/old toned name.png"
    old.parent.mkdir(parents=True)
    old.write_bytes(png("green"))
    (output / "dataset.json").write_text(
        json.dumps(
            [
                {
                    "unicode": ["U+1F44B", "U+1F3FB"],
                    "name": "old toned name",
                    "apple_emoji": {"image_path": str(old)},
                }
            ]
        )
    )
    assert run(output, sources, "apple") == 0
    entries = generate_emoji_dataset.load_entries(output)
    assert entries[1]["apple_emoji"]["image_path"] == str(old)
    assert old.read_bytes() == expected


def test_rate_limit_preserves_output_and_cached_download_resumes_later(output, sources):
    sources.vendor("apple", "red")
    source = "source/apple/123/waving-hand_light-skin-tone_1f44b-1f3fb_1f3fb.png"
    sources.catalogs["apple"]["items"][0]["images"].append(
        {
            "slug": "waving-hand-light-skin-tone",
            "image": {"source": source},
            "status": "NEW",
        }
    )
    url = f"https://em-content.zobj.net/{source}"
    sources.images[url] = response(b"limited", 429, {"Retry-After": "3600"})
    output.mkdir(parents=True)
    index = output / "dataset.json"
    index.write_text("[]\n")
    assert run(output, sources, "apple") == 1
    assert index.read_text() == "[]\n"
    # A second run can use the first completed download without requesting it again.
    del sources.images[
        "https://em-content.zobj.net/source/apple/123/grinning-face_1f600.png"
    ]
    sources.images[url] = png("blue")
    assert run(output, sources, "apple") == 0
    assert len(json.loads(index.read_text())) == 2


def test_symbol_keycaps_have_readable_distinct_names_and_images(output, sources):
    sources.vendor("apple", "red")
    sources.unicode = "# Version: 17.0\n0023 FE0F 20E3 ; fully-qualified # #️⃣ E0.6 keycap: #\n002A FE0F 20E3 ; fully-qualified # *️⃣ E2.0 keycap: *\n"
    images = []
    expected = []
    for code, color in [("23", "red"), ("2a", "blue")]:
        source = f"source/apple/123/keycap_{code}-fe0f-20e3.png"
        images.append({"slug": "keycap", "image": {"source": source}, "status": "NEW"})
        data = png(color)
        sources.images[f"https://em-content.zobj.net/{source}"] = data
        expected.append(data)
    sources.catalogs["apple"]["items"] = [{"images": images}]
    assert run(output, sources, "apple") == 0
    entries = generate_emoji_dataset.load_entries(output)
    paths = [Path(e["apple_emoji"]["image_path"]) for e in entries]
    assert [e["name"] for e in entries] == ["keycap number sign", "keycap asterisk"]
    assert [e["cldr_name"] for e in entries] == ["keycap: #", "keycap: *"]
    assert [p.name for p in paths] == ["keycap number sign.png", "keycap asterisk.png"]
    assert paths[0] != paths[1]
    assert [path.read_bytes() for path in paths] == expected


def test_missing_new_artwork_preserves_legacy_file_with_unverified_source(
    output, sources
):
    sources.vendor("apple", "red")
    legacy = output / "images/apple/waving hand light skin tone.png"
    legacy.parent.mkdir(parents=True)
    old_image = png("green")
    legacy.write_bytes(old_image)
    (output / "dataset.json").write_text("[]")
    assert run(output, sources, "apple") == 0
    entries = generate_emoji_dataset.load_entries(output)
    retained = entries[1]["apple_emoji"]
    assert Path(retained["image_path"]).read_bytes() == old_image
    assert retained["source"] == {
        "vendor": "apple",
        "release": None,
        "url": None,
        "verified": False,
    }


def test_unicode_index_uses_selected_vendor_artwork_with_source_metadata(
    output, sources
):
    apple = sources.vendor("apple", "red")
    google = sources.vendor("noto-color-emoji", "blue")
    assert run(output, sources, "apple", "google") == 0
    entries = generate_emoji_dataset.load_entries(output)
    assert [item["unicode"] for item in entries] == [
        ["U+1F600"],
        ["U+1F44B", "U+1F3FB"],
    ]
    for vendor, expected in [("apple", apple), ("google", google)]:
        image = entries[0][f"{vendor}_emoji"]
        assert Path(image["image_path"]).read_bytes() == expected
        assert image["source"]["vendor"] == vendor
        assert image["source"]["sha256"] == hashlib.sha256(expected).hexdigest()


def test_unexpected_unicode_response_does_not_replace_existing_index(output):
    response = requests.Response()
    response.status_code = 200
    response._content = b"<html>Temporarily unavailable</html>"
    output.mkdir(parents=True)
    index = output / "dataset.json"
    index.write_text("[]\n")
    with patch.object(requests.Session, "get", return_value=response):
        status = generate_emoji_dataset.main(
            ["--output", str(output), "--vendor", "apple"]
        )
    assert status == 1
    assert index.read_text() == "[]\n"


def test_unavailable_unicode_index_leaves_dataset_untouched(output):
    output.mkdir(parents=True)
    index = output / "dataset.json"
    index.write_text("[]\n")
    with patch.object(
        requests.Session, "get", side_effect=requests.ConnectionError("offline")
    ):
        status = generate_emoji_dataset.main(
            ["--output", str(output), "--vendor", "apple"]
        )
    assert status == 1
    assert index.read_text() == "[]\n"
    assert list(output.iterdir()) == [index]
