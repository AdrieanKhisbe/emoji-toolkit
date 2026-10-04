# CLI specification

Status: agreed implementation baseline; confirmed by the user in Q31 on 2026-09-30.

This document develops the draft in TODO.md. For the CLI, it supersedes conflicting decisions in docs/intended-change.md: bundled installation of all vendors, Apple as the initial default, `emoji get` as the primary invocation, and deferral of persistent skin-tone preferences.

## Confirmed decisions

- Use `emoji SHORTCODE` for lookup and `emoji install` to install resources separately from the program. Use Click. macOS/Linux and initial program installation through Git with uv/pipx remain intended.
- Accept GitHub-compatible shortcodes with or without surrounding colons, treating hyphens and underscores equivalently.
- Keep each vendor's artwork in a separate collection, sharing one Unicode/shortcode index. Installing one vendor does not overwrite another.
- Use `~/.config/emojies/` for preferences and `~/.local/share/emojies/` for resources, respecting configuration/data location environment overrides. The `emojies` spelling is intentional for now; renaming to `emoji` remains possible.
- Vendor precedence: explicit `--vendor`, then `EMOJI_VENDOR`, then the saved default. The first successfully installed vendor becomes the initial default. No automatic vendor substitution for missing artwork.
- Default lookup output is the absolute original-image path. `--url` outputs the existing PNG preview data URL, fitted within 72×72 pixels. `--url-file` outputs the absolute path to a saved `.url` containing that same URL. `--size` is deferred.
- Install image files read-only and replace spaces with underscores in installed filenames. Preserve repository filenames independently.
- Installing an already installed vendor reports that fact without updating it. Require `--update` for replacement, preparing and validating the replacement before switching; a failed update preserves the installation.
- With no vendor arguments, interactive installation offers multi-selection. In noninteractive use, fail with instructions rather than prompting. Support repeated `--vendor` and `--all`.
- Support saved default skin tone and per-request `--skin-tone`. Ignore a valid but inapplicable tone, whether configured or explicit; invalid option values are errors. `--skin-tone none` requests the unmodified emoji. An already toned input overrides the configured default; an explicit tone flag overrides the input's tone, including removing it with `none`.
- Provide `emoji config set vendor apple`, `emoji config set skin-tone dark`, `emoji config show`, and `emoji config unset skin-tone`.
- Keep stdout exclusively for lookup results. Send decorated prompts and diagnostics to stderr. Missing installation fails with setup instructions.
- When installing several vendors initially, the first specified/selected vendor becomes the default; `--all` puts Apple first. Later installations do not change the default automatically.
- Distribute a separate archive for each vendor through GitHub Releases, alongside a shared index. Include a bundle-building command in v1; resource release publishing is manual initially. No automatic publishing on dataset changes.
- Batch installation succeeds or fails per vendor: preserve successful installations and previous versions of failed vendors, report failures, and exit nonzero if any vendor fails. Use the retry policy below.
- Accept shortcodes only in v1. Literal emoji, arbitrary names, and Unicode-code notation are excluded. Emojis without an alias remain inaccessible until an alias is provided.
- Retry installation downloads up to three total attempts for connection failures, timeouts, HTTP 429, and server errors, waiting approximately 1 then 2 seconds, plus a small random delay (jitter). Honor Retry-After up to 60 seconds; longer waits stop with instructions. Do not retry permanent errors such as 404.
- Pin each installation to an immutable resource release and retain its matching lookup metadata. Different vendors may use different releases; share index files among installations from the same release. Installing/updating one vendor never silently changes another vendor's aliases or artwork.
- `emoji install --update` updates all installed vendors; explicit `--vendor` restricts the selection. With no installed vendors, give setup instructions.
- Reject configuring an uninstalled default vendor with installation instructions. Unsetting the default selects the earliest-installed remaining vendor, or leaves it unset when none are installed.
- Bare reserved command words invoke commands; surrounding colons force shortcode lookup. `--data-url` aliases `--url`; no `--format` option is planned for v1.
- Include `emoji list [QUERY] [--vendor VENDOR]` to discover available shortcodes and `emoji status` to show installed vendors, resource versions, and the default. Listing searches aliases and full emoji names by case-insensitive substring, and prints accepted shortcodes (including aliases) one per line in alphabetical order, limited to available artwork for the selected vendor. No fuzzy matching or interactive picking in v1.
- Select the latest compatible resource release by default, with `--release VERSION` for an explicit immutable release. Resolve the release once per install command so all requested vendors use the same snapshot. An installed vendor is changed only with `--update`, even when a release is explicitly requested.
- Vendor updates preserve existing installed filenames and paths, replacing their contents in place. Persist the Unicode-to-installed-path mapping across updates rather than renaming existing files when upstream names change. Validate replacements before publication and restore the previous installation on failure; no version-specific paths are returned to callers.
- Validate bundles both when building and installing them. Reject corrupt images, non-PNG contents under PNG filenames, and checksum mismatches for the affected vendor, preserving its previous installation. Do not silently repair distributed artwork on users' machines.
- Set up a GitHub Actions workflow for the test suite as part of v1.

## Local testing additions

- `emoji config set vendor` exposes the seven identifiers as Click choices, including help, validation, and completion. Skin-tone values also use Click choices.
- `emoji install --local-override PATH` reads the source dataset directly; `--local-overidde` is accepted as an alias. Use the normal installer validation, vendor isolation, stable paths, and explicit `--update` rules. Do not modify source files.
- Local installation uses `--aliases PATH` for an offline gemoji input, or downloads the pinned GitHub metadata if omitted. Mark installed versions as `local:<source path>`; this testing mode bypasses GitHub resource releases and cannot be combined with `--release`.

## Verified edge cases

- The keycap name collision has been fixed: #️⃣ is `keycap number sign` and *️⃣ is `keycap asterisk`, with corresponding PNG filenames in all seven vendors. Their CLDR labels remain `keycap: #` and `keycap: *`. Installed basenames preserve these distinctions while replacing spaces with underscores.
- The two legacy Windows arrow GIFs have been replaced with genuine 512×512 PNGs from Windows 11 22H2. Emojipedia marks them removed starting with 23H2; current releases omit them. Their source metadata records the historical release, consistent with ADR 0001.

## V1 boundary

Include Git-based program installation, manual resource bundle distribution, per-vendor installation/update, shortcode lookup, configuration, listing, status, and GitHub Actions tests.

Defer vendor removal, custom emojis, configurable image sizes, interactive picking, and a Homebrew formula. Program installation must support the agreed uv/pipx flow; broader packaging/distribution work can follow.

## Final confirmation

The user confirmed shared understanding in Q31. The v1 specification is agreed; implementation remains a separate TODO step. This confirmation does not authorize a commit or publication.
