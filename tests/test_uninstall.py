"""Exercise uninstall behavior through the CLI."""

import json
from pathlib import Path
import pytest
from .helpers import build, invoke, png


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
