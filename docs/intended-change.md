# Intended change

The CLI decisions below are historical where they conflict with the ongoing [CLI specification](cli-spec.md), developed from the revised TODO draft. Dataset regeneration decisions remain applicable.

Status: repository setup and vendor regeneration implemented. CLI and installation work remain pending. Literal-emoji fallback remains tentative.

## Settled intent

- Provide an easily installed CLI for terminal power users, including notification-tool integrations.
- Support macOS and Linux, with installation through Python tooling such as uv or pipx.
- Select emojis by GitHub-compatible shortcode, accepting aliases with or without surrounding colons.
- Return a PNG filepath or data URL content.
- Version the images in this repository and include all seven vendors in the initial installation for offline use.
- Refresh existing artwork using the replacement vendor-image acquisition method. This supersedes the initial preservation requirement.
- Keep Unicode as the emoji index. Emojipedia is the preferred replacement image source; alternatives remain open.
- Retain the vendor identifiers apple, emojione, facebook, google, samsung, twitter, and windows.
- Default to Apple, allow configuration of the default vendor, and report missing artwork as an error without automatic vendor substitution.
- Defer fzf selection and image previews.
- Keep existing image paths stable. Legacy collisions where two emojis share a path require a Unicode-suffixed path for the second image. Store the common Unicode index in `dataset.json` and artwork records in `vendors/<vendor>.json`, joined by full Unicode sequence. Each vendor record contains `unicode`, `image_path`, per-image `source` metadata, and a PNG preview `data_uri` fitted within 72×72 pixels without palette reduction or upscaling. Keep each generated JSON below 100,000,000 bytes. CLI data URLs can still be generated on demand from original PNGs.
- Select the latest available artwork for each vendor at refresh time recording per-image source metadata in vendor files. CLI lookups use the packaged images.
- Cover all fully qualified Unicode emoji sequences, including skin tones, gender variants, flags, and joined sequences, even where vendor artwork is unavailable.
- Refresh each vendor atomically: validate downloads before replacing its artwork; retain its previous images if the refresh fails. Successful vendors can update independently.
- Provide `emoji get SHORTCODE`, `--vendor VENDOR`, `--format data-url`, and the shortcut `--data-url`, plus `emoji list`.
- Print an absolute PNG path by default. Keep stdout for requested output, report errors on stderr, and exit nonzero on failure.
- Allow `EMOJI_VENDOR` to override the default vendor.
- Distribute through Git installation with uv/pipx first; use Poetry for contributor dependency management.
- Preserve downloaded PNG dimensions and transparency.
- Select skin tone with an optional per-command flag; persistent skin-tone configuration is deferred.
- Accept `--skin-tone light|medium-light|medium|medium-dark|dark`. Omission selects the unmodified emoji; unsupported combinations return an error. Apply the same tone to everyone in supported multi-person combinations; mixed-tone selection is deferred.
- Preserve an emoji's previous vendor artwork when the newly selected release genuinely lacks it. Keep per-image `source` metadata in vendor files, consistent with ADR 0001. Preserve existing provenance for retained artwork; mark unknown legacy provenance with null release/URL and `verified: false`.
- Map `emojione` to JoyPixels, `google` to classic flat Noto Color Emoji, `twitter` to Twitter/X artwork, and `windows` to Windows 2D artwork. Select the latest release within each design family; use the latest Apple, Facebook, and Samsung releases for the other identifiers.

## Final confirmation

- Literal-emoji input is tentatively included as an optional fallback for emojis without GitHub aliases. The user expressed reservations; it is not a requirement for ordinary shortcode lookup.
- Implementation proceeds one TODO step at a time, as authorized by the user.

## Implementation checks

- Check existing JSON consumers before simplifying its structure; preserve compatibility where needed.
- Validate actual PNG contents before accepting vendor downloads; a filename extension alone is insufficient.
- Vendor image records include `source`: vendor, release, URL, original-image SHA-256, and UTC retrieval timestamp for refreshed artwork. Cached downloads use the current refresh timestamp; do not invent historical provenance for legacy artwork.
- Repacking local JSON must work offline, preserve original PNG bytes, and retain transactional publication. Subsequent vendor refreshes must read and write the split format.

## Findings relevant to preservation

The current generator assigns vendors by table-column position. Unicode's current chart has Sample and legacy vendor columns in those positions. The working-tree Apple butterfly and cucumber images match the Sample-column images byte for byte, so their directory names do not establish Apple provenance. The existing user changes have been left intact during the interview; refreshing existing artwork is now explicitly in scope for implementation.

GitHub's [gemoji metadata](https://github.com/github/gemoji/blob/master/db/emoji.json) supplies Unicode-to-shortcode aliases, but does not enumerate skin-tone sequences. Complete Unicode coverage therefore requires a lookup policy for sequences without those aliases.

Vendor names alone do not fully select artwork: EmojiOne is now JoyPixels, Google offers classic and 3D designs, Microsoft offers distinct styles, and Twitter/X artwork is distinct from independently maintained Twemoji. The selected mappings are recorded above.
