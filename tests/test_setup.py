"""Exercise setup behavior through the CLI."""

import json
from pathlib import Path
import pytest
from .helpers import build, invoke, tamper_bundle


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
