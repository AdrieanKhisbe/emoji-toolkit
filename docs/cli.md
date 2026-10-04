# Emoji CLI

Install the program with Python 3.11+ through either tool:

```sh
uv tool install git+https://github.com/AdrieanKhisbe/emoji-toolkit.git
# or
pipx install git+https://github.com/AdrieanKhisbe/emoji-toolkit.git
```

Until this branch is merged, append `@regeneration` to the Git URL.
Artwork installation requires a published compatible immutable resource release;
see [resource releases](resource-releases.md) for the manual publishing procedure.
For local testing, install directly from the source dataset instead:

```sh
poetry run emoji install --vendor apple --local-override resources/dataset
```

This reads local artwork and fetches the pinned GitHub shortcode metadata. Add
`--aliases /path/to/gemoji.json` to install entirely offline. The original typo
`--local-overidde` is also accepted. Local installation copies and validates the
artwork; it does not modify source files. `--update` is still required to replace
an installed vendor. `--local-override` cannot be combined with `--release`.

```sh
emoji install --vendor apple
emoji grinning                         # absolute original PNG path
emoji :grinning: --url                  # PNG preview data URL, at most 72×72
emoji --url grinning                    # options may precede the shortcode
emoji grinning --data-url               # alias for --url
emoji grinning --url-file               # path to a file containing the URL
emoji wave --skin-tone dark
emoji list hand
emoji status
```

Shortcodes follow GitHub aliases; surrounding colons are optional and hyphens
and underscores are equivalent. Names, literal emojis, and Unicode notation
are not accepted. Surround command words with colons to look them up as aliases:
`emoji :install:`. A missing alias or artwork returns a nonzero exit code.
Diagnostics and prompts go to stderr; lookup prints only its result to stdout.

```sh
emoji install                          # interactive comma-separated vendor selection
emoji install --vendor google --vendor twitter
emoji install --all
emoji install --update                 # all installed vendors
emoji install --vendor apple --update
emoji install --vendor apple --update --release resources-2026-09-30
emoji config set vendor --help         # list accepted vendors
emoji config set vendor apple
emoji config set skin-tone dark
emoji config show
emoji config unset skin-tone
```

The first successfully installed vendor becomes the default. `--all` starts
with Apple. Select artwork using `--vendor`, then `EMOJI_VENDOR`, then the saved
default, in that order. Vendors are never substituted automatically. Installing
an existing vendor does nothing unless `--update` is given. Without arguments,
noninteractive installation fails with setup instructions.

Skin tones are `none`, `light`, `medium-light`, `medium`, `medium-dark`, and `dark`.
A toned shortcode overrides the saved tone; an explicit `--skin-tone` overrides
both. `none` removes the tone. Valid but inapplicable tones are ignored. Where
multiple people can be toned, the flag applies the same tone to everyone.
A supported variant missing from the selected vendor is an error.

Preferences and resources respect `XDG_CONFIG_HOME` and `XDG_DATA_HOME`. Defaults
are `~/.config/emojies/` and `~/.local/share/emojies/`. Installed filenames use
underscores for spaces and remain stable across updates. Lookup needs no network.
