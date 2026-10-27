"""Exercise store locking across real processes on every supported OS."""

import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from emoji_dataset.store import Store, remove_artwork


@pytest.mark.parametrize("holder_exclusive", [False, True])
@pytest.mark.parametrize("reader_exclusive", [False, True])
def test_store_readers_share_lock_and_writers_wait(
    tmp_path, monkeypatch, holder_exclusive, reader_exclusive
):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    script = """
import sys
from emoji_dataset.store import Store
print('ready', flush=True)
with Store().locked(exclusive=sys.argv[1] == 'True'):
    print('acquired', flush=True)
"""
    process = None
    try:
        with Store().locked(exclusive=holder_exclusive):
            process = subprocess.Popen(
                [sys.executable, "-c", script, str(reader_exclusive)],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            assert process.stdout.readline() == "ready\n"
            if not holder_exclusive and not reader_exclusive:
                output, errors = process.communicate(timeout=10)
                assert process.returncode == 0, errors
                assert output == "acquired\n"
            else:
                with pytest.raises(subprocess.TimeoutExpired):
                    process.wait(timeout=0.2)
        output, errors = process.communicate(timeout=10)
        assert process.returncode == 0, errors
        assert output == "acquired\n"
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate()


def test_store_releases_lock_when_operation_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="interrupted"):
        with Store().locked():
            raise ValueError("interrupted")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from emoji_dataset.store import Store\nwith Store().locked(): print('acquired')",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "acquired\n"


def test_removal_handles_readonly_artwork(tmp_path):
    artwork = tmp_path / "vendor"
    artwork.mkdir()
    image = artwork / "emoji.png"
    image.write_bytes(b"artwork")
    image.chmod(stat.S_IREAD)
    remove_artwork(artwork)
    assert not artwork.exists()


def test_generator_refuses_concurrent_refresh_and_recovers(tmp_path):
    import portalocker

    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "dataset.json").write_text("[]")
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "src/generate_emoji_dataset.py"),
        "--output",
        str(dataset),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--repack",
    ]
    with portalocker.Lock(
        tmp_path / ".dataset-refresh.lock",
        mode="a",
        flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
    ):
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        assert result.returncode == 1
        assert "Regeneration failed" in result.stderr
        assert "Traceback" not in result.stderr
        assert (dataset / "dataset.json").read_text() == "[]"
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
