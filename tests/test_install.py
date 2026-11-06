"""Exercise install behavior through the CLI."""

import hashlib
import json
from pathlib import Path
import pytest
import requests
from .helpers import build, corrupt_png_crc, invoke, png, tamper_bundle


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
