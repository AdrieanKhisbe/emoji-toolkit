"""Exercise bundles behavior through the CLI."""

import base64
import json
import zipfile
import pytest
from click.testing import CliRunner
from PIL import Image
from .helpers import build, png


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
