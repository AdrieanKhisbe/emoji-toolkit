# Emoji CLI

Install the program with Python 3.11+ through either tool:

```sh
uv tool install git+https://github.com/AdrieanKhisbe/emoji-toolkit.git@v0.1.0
# or
pipx install git+https://github.com/AdrieanKhisbe/emoji-toolkit.git@v0.1.0
```

Artwork installation requires a published compatible immutable resource release;
see [resource releases](resource-releases.md) for the manual publishing procedure.

`emoji setup` installs Apple on macOS, Windows on Windows, and Google on Linux,
and selects it as the default. It confirms installation interactively; pass
`--yes` for unattended use. On an unknown OS with no installed artwork, choose
one vendor interactively or use `emoji install --vendor VENDOR` noninteractively.
Bare `emoji install` keeps its multi-vendor picker.

Setup accepts only `--yes`. If the OS vendor is already installed, setup reports
it without downloading, prompting, or changing the current default. On an unknown
OS, any installed vendor means setup is already complete. If other vendors are
installed but the OS vendor is absent, setup fails with an explicit command such
as `emoji install --vendor apple --use-as-default`.

Updates and advanced resource options (`--release`, `--local-override`, and
`--aliases`), vendor selection, and `--all` belong to `install`.

```sh
emoji setup
emoji setup --yes
emoji install --update                 # refresh installed vendors only
```

Store locking supports macOS, Linux, and native Windows, including concurrent
readers and exclusive updates. Windows dependencies are installed automatically.
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
emoji install --vendor google --use-as-default  # install and select the default
emoji grinning                          # absolute original PNG path
emoji get :satisfied:                   # explicit lookup (alias of lookup)
emoji :grinning: --url                  # PNG preview data URL, at most 72×72
emoji --url grinning                    # options may precede the shortcode
emoji grinning --data-url               # alias for --url
emoji grinning --url --size 128         # on-demand preview within 128×128
emoji :wink: --url-file                 # path to a file containing the URL
emoji wave --skin-tone dark
emoji list hand
emoji list wave --colon                 # :wave:
emoji list wave --emoji                 # 👋 wave (also lists matching aliases)
emoji status
```

Shortcodes follow GitHub aliases; surrounding colons are optional and hyphens
and underscores are equivalent. Names, literal emojis, and Unicode notation
are not accepted. Surround command words with colons to look them up as aliases:
`emoji :install:`. A missing alias or artwork returns a nonzero exit code.
`emoji get SHORTCODE` and `emoji lookup SHORTCODE` accept the same options as
`emoji SHORTCODE`.
Diagnostics and prompts go to stderr; lookup prints only its result to stdout.

Use `--size N` with `--url` or `--data-url` to generate a PNG preview from the
original artwork on demand. Sizes must be integers from 1 to 1024. Previews fit
within N×N pixels, preserving proportions and transparency. Small originals are
never enlarged; a larger requested size produces a warning on stderr and keeps
the original dimensions. Original images and saved previews remain unchanged.
Without `--size`, data URLs use the existing preview, at most 72×72 pixels.
`--size` requires a URL output option and cannot be used with `--url-file`.

```sh
emoji install                          # interactive comma-separated vendor selection
emoji install --vendor google --vendor twitter
emoji install --all                    # install every supported vendor
emoji install --update                 # refresh all installed artwork
emoji install --update --vendor apple  # refresh Apple artwork
emoji install --vendor apple --update --release resources-2026-09-30
emoji uninstall --vendor google
emoji uninstall --vendor apple --vendor twitter
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
noninteractive installation fails with setup instructions. `--update` refreshes
only installed vendors and fails with setup instructions when none are installed.
Use `--all` for initial installation of every supported vendor; combining it with
`--update` is an error.

Use `install --use-as-default` with exactly one selected vendor to save it as
the default after successful installation. It also works for an already
installed vendor without downloading or requiring `--update`. Other preferences
are preserved. Multiple selections, including `--all` or an update of several
installed vendors, are rejected before installation. A failed installation or
update preserves the previous default. Without the flag, defaults are unchanged.

`emoji uninstall --vendor VENDOR` removes that vendor's images, previews, and
installation metadata without prompting. Repeat `--vendor` to remove several;
an absent vendor is a successful no-op. There is no `--all` option. Removal is
offline and preserves other vendors and any shared indexes they still need.

Removing the default vendor clears the selection without choosing a replacement.
Lookup then requires `--vendor`, `EMOJI_VENDOR`, or a new saved default:

```sh
emoji config set vendor google
```

Other preferences, including skin tone, are preserved. A failed removal is
reported while remaining selected vendors are still attempted. Cleanup failures
after removal are warnings with the affected location. If saving the cleared
default fails, the vendor's artwork is restored.

Skin tones are `none`, `light`, `medium-light`, `medium`, `medium-dark`, and `dark`.
A toned shortcode overrides the saved tone; an explicit `--skin-tone` overrides
both. `none` removes the tone. Valid but inapplicable tones are ignored. Where
multiple people can be toned, the flag applies the same tone to everyone.
A supported variant missing from the selected vendor is an error.

Preferences and resources respect `XDG_CONFIG_HOME` and `XDG_DATA_HOME`. Defaults
are `~/.config/emojies/` and `~/.local/share/emojies/`. Installed filenames use
underscores for spaces and remain stable across updates. Lookup needs no network.

`emoji list [QUERY] --format plain|colon|emoji` selects the list output:

| Format | Example | Shortcut |
| --- | --- | --- |
| `plain` (default) | `wave` | |
| `colon` | `:wave:` | `--colon` |
| `emoji` | `👋 wave` | `--emoji` |

Every format keeps all matching aliases in alphabetical order, one per line,
with the same case-insensitive search and vendor filtering. Emoji are Unicode
characters rendered by your terminal, rather than vendor images. Skin tones and
joined sequences and emoji presentation selectors are retained, including with
older resource indexes. Conflicting format options are rejected; repeating
the same format through its shortcut is allowed. Empty results print nothing.
