# Emoji Toolkit

[![Version 0.1.0](https://img.shields.io/badge/version-0.1.0-blue)](pyproject.toml)
[![CI](https://github.com/AdrieanKhisbe/emoji-toolkit/actions/workflows/tests.yml/badge.svg)](https://github.com/AdrieanKhisbe/emoji-toolkit/actions/workflows/tests.yml)
[![Status: in development](https://img.shields.io/badge/status-in_development-yellow)](https://github.com/AdrieanKhisbe/emoji-toolkit/issues)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> Get emoji images or data URLs from your terminal for notifications, scripts, and everyday tools. :fishing_pole_and_fish:

Pick a vendor, look up a shortcode, and use the artwork anywhere.

## Install :cd:

Requires Python 3.11+ and `uv` or `pipx`.

```sh
uv tool install git+https://github.com/AdrieanKhisbe/emoji-toolkit.git@v0.1.0
# Or use pipx:
pipx install git+https://github.com/AdrieanKhisbe/emoji-toolkit.git@v0.1.0

emoji install --vendor apple
```

## Use it :rugby_football:

```sh
emoji smiley                         # original PNG path
# /Users/ak/.local/share/emojies/vendors/apple/grinning_face_with_big_eyes.png
emoji smiley --url                   # PNG preview data URL
# data:image/png;base64,iVBOR.....RK5CYII=

emoji wave --skin-tone dark          # choose a skin tone
emoji smiley --vendor google         # choose a vendor
emoji list hand                      # discover shortcodes
```
<!--(Faire des capture d'usage ascii-image-converter, notif, etc)-->

Shortcodes follow GitHub aliases. Colons are optional: `smiley` and
`:smiley:` work the same way. 😃
Paths point to original images; data URLs contain small previews, up to 72×72 pixels.

Your first installed vendor becomes the default. Change it or save a skin tone:

```sh
emoji config set vendor apple
emoji config set skin-tone dark
emoji install --update                 # refresh installed artwork
emoji status                           # show installed vendors and versions
```

See [all commands and options](docs/cli.md).

## Pick your artwork :rainbow:

Different Emoji images vendors are provided
Pick one:
- `apple`: [Apple](https://emojipedia.org/apple)
- `emojione`: [JoyPixels](https://emojipedia.org/joypixels)
- `facebook`: [Facebook](https://emojipedia.org/facebook)
- `google`: [Google Noto Color Emoji](https://emojipedia.org/noto-color-emoji)
- `samsung`: [Samsung](https://emojipedia.org/samsung)
- `twitter`: [Twitter / X](https://emojipedia.org/twitter)
- `windows`: [Microsoft Windows](https://emojipedia.org/microsoft)

```sh
emoji install --vendor google --vendor twitter
emoji install --all
```

The same 😃 `:smiley:`, drawn by each vendor:

| Vendor | Smiley |
| --- | :---: |
| Apple | <img src="resources/dataset/images/apple/grinning%20face%20with%20big%20eyes.png" alt="Apple smiley" width="48"> |
| JoyPixels | <img src="resources/dataset/images/emojione/grinning%20face%20with%20big%20eyes.png" alt="JoyPixels smiley" width="48"> |
| Facebook | <img src="resources/dataset/images/facebook/grinning%20face%20with%20big%20eyes.png" alt="Facebook smiley" width="48"> |
| Google | <img src="resources/dataset/images/google/grinning%20face%20with%20big%20eyes.png" alt="Google smiley" width="48"> |
| Samsung | <img src="resources/dataset/images/samsung/grinning%20face%20with%20big%20eyes.png" alt="Samsung smiley" width="48"> |
| Twitter / X | <img src="resources/dataset/images/twitter/grinning%20face%20with%20big%20eyes.png" alt="Twitter smiley" width="48"> |
| Microsoft Windows | <img src="resources/dataset/images/windows/grinning%20face%20with%20big%20eyes.png" alt="Microsoft Windows smiley" width="48"> |

## Explore the dataset :world_map:

The checked-in artwork lives in [`resources/dataset`](resources/dataset):

- `dataset.json` — the shared Unicode index.
- `vendors/<vendor>.json` — image paths, preview data URLs, and source metadata.
- `images/<vendor>/` — original artwork.

Join vendor records to the index by their `unicode` sequence. Reading the JSON
and images requires no Python dependencies.

See [dataset maintenance](docs/dataset-maintenance.md) and
[publishing resource bundles](docs/resource-releases.md).

## Contribute :handshake:

From a checkout, use Python 3.11+ and Poetry 2+:

```sh
poetry install
poetry run poe local-install            # install Apple artwork from this checkout
poetry run poe format
poetry run poe format-check
poetry run poe typecheck
poetry run poe test
```

Have a bug or an idea? [Open an issue](https://github.com/AdrieanKhisbe/emoji-toolkit/issues).
For artwork problems, include the emoji and vendor.

## License

Project code is licensed under [MIT](LICENSE). Vendor artwork retains its
respective copyrights and licenses; see [Emojipedia's licensing guide](https://emojipedia.org/licensing).
