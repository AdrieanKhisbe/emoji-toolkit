# Publishing resource releases

The `emoji` program is installed separately from artwork. It downloads only
immutable GitHub releases with a compatible `manifest.json`; lookup is offline.
No resource release is published automatically by the test workflow.

## Build

Use a pinned revision of GitHub's [gemoji metadata](https://github.com/github/gemoji)
for shortcodes. The builder records the input file's SHA-256 in the manifest.
For example, from the repository root:

```sh
curl -L --fail https://raw.githubusercontent.com/github/gemoji/fadaeaf1f1a9be82b321316a6c5502e43138b2f6/db/emoji.json -o /tmp/gemoji.json
poetry run poe build-bundles --aliases /tmp/gemoji.json \
  --release resources-2026-09-30 --output dist/resources-2026-09-30
```

By default this builds all seven vendors. Repeat `--vendor` to build a subset.
`--dataset` defaults to `resources/dataset`. Output must be a new directory;
validation failure leaves it unpublished. Existing artwork, source metadata,
and preview URLs are preserved. Invalid PNGs, invalid previews, conflicting
shortcodes, and mismatched source checksums fail the build.

The output contains `manifest.json`, `index.json`, and `<vendor>.zip` files.
Schema 1 identifies compatibility. The manifest hashes the index and archives;
each archive's `vendor.json` hashes individual PNG and `.url` files. Vendor
records retain their source metadata. The index includes names, aliases, and
skin-tone relationships derived from Unicode's CLDR labels. Unaliased emojis
are included in resources but cannot be selected directly by the v1 CLI.

## Publish manually

1. Review and commit the dataset being released.
2. Enable **release immutability** in the repository's GitHub settings.
3. Create a draft release with exactly the tag supplied to `--release`.
4. Attach **all** files from the output directory. Include the pinned gemoji
   revision and its [license](https://github.com/github/gemoji/blob/master/LICENSE)
   in the release notes, alongside the artwork provenance.
5. Publish the draft as a stable release, locking its tag and assets.

GitHub recommends attaching assets before publishing an immutable release:
[GitHub release documentation](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).
The CLI checks GitHub's immutable flag and asset digest before trusting the
manifest. Mutable releases, prereleases, and incompatible resource schemas are
not selected. A new resource version requires a new release tag.

## Installation behavior

`emoji install` resolves one release for the whole invocation. A failure affects
only that vendor; successful vendors stay installed. Each vendor retains its
release's index, shared by content hash with other vendors using the same index.

Installed files live at stable paths under `$XDG_DATA_HOME/emojies/vendors/`
(default `~/.local/share/emojies/vendors/`). An update stages and validates a
replacement, then replaces the vendor directory at the same path. A persisted
Unicode-to-filename map preserves existing paths even after upstream renames.
Read-only PNG and `.url` files are replaced together. Preferences live in
`$XDG_CONFIG_HOME/emojies/config.json` (default `~/.config/emojies/config.json`).

Commands coordinate local publication using a file lock; network downloads do
not block offline lookups. If a process is forcibly
terminated during the directory swap, `.VENDOR-previous` in the vendors directory
contains the recovery copy. Restore that directory to `VENDOR` before retrying.
A failed normal update rolls back automatically. A cleanup warning after success
can leave a `.VENDOR-obsolete-*` directory; it contains unused old files and does
not block subsequent updates. Previously installed indexes
are kept so another vendor's aliases never change as a side effect of an update.
