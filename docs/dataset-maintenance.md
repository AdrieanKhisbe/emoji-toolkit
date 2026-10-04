# Dataset maintenance

[`src/generate_emoji_dataset.py`](../src/generate_emoji_dataset.py) reads Unicode's fully qualified emoji index
and downloads the latest released vendor artwork from Emojipedia. Each PNG is
validated before publication. `resources/dataset/dataset.json` contains the shared Unicode
index. Each `resources/dataset/vendors/<vendor>.json` contains an array of image records
with `unicode`, `image_path`, `data_uri`, and `source`; join records to the index by their
full `unicode` sequence. Missing artwork has no vendor record.

Image paths refer to the unchanged, full-resolution PNGs. Data URLs embed PNG
previews fitted within 72×72 pixels, preserving aspect ratio and transparency,
without palette reduction or upscaling. Each generated JSON must stay below
100 MB (100,000,000 bytes), otherwise publication is cancelled. Per-image `source` records the vendor, release, URL, SHA-256 of the original
image (not the preview), and UTC retrieval timestamp. Cached downloads record
the time they are reused by the refresh. Existing provenance is retained for
unchanged artwork; legacy images of unknown origin have null release/URL and
`verified: false`. `unicode-source.json` records the Unicode index version
and source. This split replaces the previous embedded `<vendor>_emoji` fields.
Some retained legacy files have a `.png` extension but contain GIF data; their
bytes remain untouched and their previews use the first frame, encoded as PNG.

```sh
poetry run poe regenerate
poetry run poe regenerate --vendor apple
# Rebuild local previews and split a legacy index without downloading:
poetry run poe regenerate --repack
# Small refresh in a separate directory:
poetry run poe regenerate --output /tmp/emoji-sample --vendor apple --emoji U+1F600
poetry run poe test
```

The local identifiers remain `apple`, `emojione` (JoyPixels), `facebook`,
`google` (classic Noto Color Emoji), `samsung`, `twitter` (Twitter/X), and
`windows` (Microsoft Windows 2D). Repeat `--vendor` or `--emoji` to select several;
`--emoji` limits artwork downloads while retaining the complete Unicode index.

A failed download leaves that vendor unchanged; other vendors can still update.
Artwork missing from a new release is retained. Its existing source metadata is retained. Existing indexed image paths remain stable except for legacy collisions: when two emojis share a
path, the second receives a Unicode suffix and a copy of the retained image.

Validated downloads are cached in `.cache/emoji-dataset/` for later retries.
Requests are spaced by `--request-delay` seconds (default: 0.25). HTTP 429 stops
requests to that host for the run and reports `Retry-After`; wait that long before
retrying. The public website endpoint currently requires no authentication.
It is not a stable public API; source-format changes cause the refresh to fail.

Publication uses a staged directory and rollback, with a lock against concurrent
generators. If interrupted during publication, a sibling `resources/.dataset-previous`
recovery copy may remain (named after `--output`). Inspect and restore or move it
before retrying. Keep `--output` dedicated to the dataset and the cache outside it.
