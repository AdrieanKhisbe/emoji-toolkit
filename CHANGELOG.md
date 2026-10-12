# Change Log

All notable changes to *Emoji Toolkit* will be documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased][unreleased]

### Added

- `install --use-as-default` selects a single vendor after successful installation or selects an already installed vendor without downloading ([#3]).
- On-demand PNG preview sizes with `--url --size N` (1–1024 pixels), preserving proportions and transparency without enlarging original artwork ([#2]).
- 🎯 Explicit lookup commands: `emoji get :wave:` and `emoji lookup :wave:`, with the same options as `emoji :wave:`.

### Changed

- Installation instructions now use the published `emoji-toolkit` package on PyPI.
- The README version badge links to PyPI and displays the published version.

## [0.1.0] - 2026-10-04

First CLI release.

### Added

- 😃 Offline lookup by GitHub shortcode, returning original PNG paths or preview data URLs.
- 🎨 Seven separately installable artwork vendors: Apple, JoyPixels, Facebook, Google, Samsung, Twitter / X, and Microsoft Windows.
- Skin-tone selection and saved defaults for vendor and skin tone.
- Commands to install and update artwork, discover shortcodes, manage preferences, and check installed versions.
- Validated artwork updates that preserve image paths and handle vendor failures independently.
- A Unicode emoji index and vendor datasets with artwork provenance, refreshed from Emojipedia.
- Python package published as `emoji-toolkit`, with the `emoji` terminal command and separate resource bundles.
- MIT license for project code; vendor artwork retains its respective copyrights and licenses.

[unreleased]: https://github.com/AdrieanKhisbe/emoji-toolkit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/AdrieanKhisbe/emoji-toolkit/releases/tag/v0.1.0
[#2]: https://github.com/AdrieanKhisbe/emoji-toolkit/issues/2
[#3]: https://github.com/AdrieanKhisbe/emoji-toolkit/issues/3
