"""Prepare a local source dataset for the normal validated installer."""

from pathlib import Path

from .bundles import build_index, build_vendor
from .format import encode_json

GEMOJI_URL = "https://raw.githubusercontent.com/github/gemoji/fadaeaf1f1a9be82b321316a6c5502e43138b2f6/db/emoji.json"


class LocalDataset:
    def __init__(self, dataset: Path, aliases: Path, workspace: Path) -> None:
        self.dataset = dataset.resolve()
        if not (self.dataset / "dataset.json").is_file():
            raise ValueError(
                "Local override must point to the source dataset directory containing dataset.json (for example resources/dataset)"
            )
        self.workspace = workspace
        self.index = build_index(self.dataset, aliases)
        self.index_bytes = encode_json(self.index)
        self.release = f"local:{self.dataset}"

    def bundle(self, vendor: str) -> bytes:
        path = self.workspace / f"{vendor}.zip"
        build_vendor(self.dataset, vendor, path, self.index)
        return path.read_bytes()
