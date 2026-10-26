"""Command-line access to offline vendor artwork."""

from contextlib import ExitStack, contextmanager, nullcontext
import sys
import platform
import tempfile
from pathlib import Path
import zipfile
from typing import Iterator

import click
import requests

from .downloads import ReleaseClient
from .local import GEMOJI_URL, LocalDataset
from .format import TONES, VENDORS, shortcode, sized_data_url
from .store import Store, atomic_json


@contextmanager
def operation(*, write: bool = False, lock: bool = True) -> Iterator[Store]:
    try:
        store = Store()
        with store.locked(exclusive=write) if lock else nullcontext():
            yield store
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        requests.RequestException,
        zipfile.BadZipFile,
    ) as error:
        raise click.ClickException(str(error)) from error


@click.command()
@click.argument("alias")
@click.option("--vendor", type=click.Choice(VENDORS))
@click.option("--url", "--data-url", "as_url", is_flag=True)
@click.option("--url-file", is_flag=True)
@click.option(
    "--size",
    type=click.IntRange(1, 1024),
    help="Fit an on-demand PNG preview within SIZE×SIZE pixels (requires --url).",
)
@click.option("--skin-tone", type=click.Choice(TONES))
def lookup(
    alias: str,
    vendor: str | None,
    as_url: bool,
    url_file: bool,
    size: int | None,
    skin_tone: str | None,
) -> None:
    """Print an absolute PNG path (or preview URL) for a GitHub shortcode."""
    if size is not None:
        if url_file:
            raise click.UsageError("--size cannot be combined with --url-file")
        if not as_url:
            raise click.UsageError("--size requires --url or --data-url")
    if as_url and url_file:
        raise click.UsageError("Choose either --url or --url-file")
    with operation() as store:
        vendor = store.vendor(vendor)
        index, records = store.collection(vendor)
        key = index["aliases"].get(shortcode(alias))
        if not key:
            raise ValueError(
                f"Unknown shortcode {alias!r}. Use emoji list to find one."
            )
        entry = index["entries"][key]
        tone = skin_tone
        if tone is None and entry["base"] == key:
            tone = store.preferences().get("skin-tone")
        if tone is not None:
            base = index["entries"][entry["base"]]
            if len(base.get("tones", {})) > 1:
                replacement = base["tones"].get(tone)
                if replacement is None:
                    raise ValueError(f"No {tone} skin-tone variant for {alias}.")
                key = replacement
        if key not in records:
            raise ValueError(f"No {vendor} artwork for {alias}.")
        path = store.data / "vendors" / vendor / records[key]["filename"]
        if size is None and (as_url or url_file):
            path = path.with_suffix(".url")
        if not path.is_file():
            raise ValueError(
                f"Missing artwork. Run emoji install --vendor {vendor} --update."
            )
        if size is not None:
            url, dimensions = sized_data_url(path, size)
            if size > max(dimensions):
                click.echo(
                    f"⚠️ Requested size {size} exceeds original artwork "
                    f"({dimensions[0]}×{dimensions[1]}); keeping original dimensions.",
                    err=True,
                )
            click.echo(url)
        else:
            click.echo(path.read_text() if as_url else str(path))


class EmojiGroup(click.Group):
    def parse_args(self, ctx, args):
        # GitHub's thumbs-down alias is a positional value, not a short option.
        if args and args[0] == "-1":
            args = [":-1:", *args[1:]]
        lookup_options = {
            option
            for param in lookup.params
            if isinstance(param, click.Option)
            for option in param.opts
        }
        if args and args[0].split("=", 1)[0] in lookup_options:
            # Leave lookup options for the lookup command's own Click parser.
            args = ["--", *args]
        return super().parse_args(ctx, args)

    def resolve_command(self, ctx, args):
        if args and args[0] not in self.commands:
            return "lookup", lookup, [":-1:" if arg == "-1" else arg for arg in args]
        return super().resolve_command(ctx, args)


@click.group(cls=EmojiGroup, context_settings={"allow_interspersed_args": False})
@click.version_option("0.1.0")
def cli() -> None:
    """Emoji artwork for terminal tools. Lookup: emoji SHORTCODE [OPTIONS]."""


cli.add_command(lookup)
cli.add_command(lookup, "get")


def pick_vendors(*, single: bool = False) -> list[str]:
    if not sys.stdin.isatty():
        raise ValueError("Select a vendor: emoji install --vendor apple")
    click.echo("📦 Available vendors: " + ", ".join(VENDORS), err=True)
    if single:
        vendor = click.prompt("Select vendor", err=True)
        if vendor not in VENDORS:
            raise ValueError(
                "Choose exactly one vendor identifier from the displayed list"
            )
        return [vendor]
    answer = click.prompt("Select vendors (comma-separated)", err=True)
    selected = list(dict.fromkeys(part.strip() for part in answer.split(",")))
    if any(name not in VENDORS for name in selected):
        raise ValueError("Choose vendor identifiers from the displayed list")
    return selected


@cli.command()
@click.option("--vendor", multiple=True, type=click.Choice(VENDORS))
@click.option("--release", "tag")
@click.option("--all", "all_vendors", is_flag=True)
@click.option("--update", is_flag=True)
@click.option(
    "--use-as-default",
    is_flag=True,
    help="Set the single selected vendor as default after successful installation.",
)
@click.option(
    "--local-override",
    "--local-overidde",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Install from a source dataset directory instead of GitHub Releases.",
)
@click.option(
    "--aliases",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Local gemoji JSON for --local-override; otherwise fetch pinned metadata.",
)
def install(
    vendor: tuple[str, ...],
    tag: str | None,
    all_vendors: bool,
    update: bool,
    use_as_default: bool,
    local_override: Path | None,
    aliases: Path | None,
) -> None:
    """Install or explicitly update vendor artwork from a resource release."""
    if update and all_vendors:
        raise click.UsageError(
            "Use --update without --all to refresh installed vendors"
        )
    if all_vendors and vendor:
        raise click.UsageError("Choose --all or --vendor")
    if local_override and tag:
        raise click.UsageError("Choose --local-override or --release")
    if aliases and not local_override:
        raise click.UsageError("--aliases requires --local-override")
    with operation(lock=False) as store, ExitStack() as stack:
        selected = list(dict.fromkeys(VENDORS if all_vendors else vendor))
        with store.locked(exclusive=False):
            installed = store.installed()
        if not selected:
            if update:
                selected = list(installed)
                if not selected:
                    raise ValueError(
                        "No vendors installed. Run emoji setup or emoji install --vendor VENDOR."
                    )
            elif sys.stdin.isatty():
                selected = pick_vendors()
        if not selected:
            raise ValueError("Select a vendor: emoji install --vendor apple")
        if use_as_default and len(selected) != 1:
            raise click.UsageError("--use-as-default requires exactly one vendor")
        pending = []
        for name in selected:
            if name in installed and not update:
                click.echo(
                    f"📦 {name} already installed; use --update to replace it.",
                    err=True,
                )
            else:
                pending.append(name)
        if not pending:
            if use_as_default:
                save_preference("vendor", selected[0])
            return
        client = ReleaseClient()
        local = None
        if local_override:
            if not (local_override / "dataset.json").is_file():
                raise ValueError(
                    "Local override must contain dataset.json (for example resources/dataset)"
                )
            workspace = Path(
                stack.enter_context(tempfile.TemporaryDirectory(prefix="emoji-local-"))
            )
            if aliases is None:
                click.echo(
                    "📥 Fetching pinned GitHub shortcode metadata (use --aliases for offline installation).",
                    err=True,
                )
                aliases = workspace / "gemoji.json"
                aliases.write_bytes(client.download(GEMOJI_URL))
            local = LocalDataset(local_override, aliases, workspace)
            index = local.index_bytes
            release_name = local.release
        else:
            release, manifest = client.resolve(tag)
            release_name = release["tag_name"]
            index = client.asset(
                release, manifest["index"]["file"], manifest["index"]["sha256"]
            )
        failures = []
        for name in pending:
            try:
                if local is not None:
                    bundle = local.bundle(name)
                else:
                    if name not in manifest["vendors"]:
                        raise ValueError("vendor missing from this resource release")
                    asset = manifest["vendors"][name]
                    bundle = client.asset(release, asset["file"], asset["sha256"])
                with store.locked():
                    if name in store.installed() and not update:
                        click.echo(
                            f"📦 {name} already installed; use --update to replace it.",
                            err=True,
                        )
                        continue
                    warning = store.install(name, release_name, index, bundle)
                if warning:
                    click.echo(f"⚠️ {warning}", err=True)
                click.echo(f"📦 Installed {name} ({release_name})", err=True)
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                requests.RequestException,
                zipfile.BadZipFile,
            ) as error:
                failures.append(name)
                click.echo(f"❌ {name}: {error}", err=True)
        if failures:
            raise ValueError("Installation failed for: " + ", ".join(failures))
        if use_as_default:
            save_preference("vendor", selected[0])


@cli.command()
@click.option("--yes", is_flag=True, help="Skip confirmation for initial installation.")
@click.pass_context
def setup(
    ctx: click.Context,
    yes: bool,
) -> None:
    """Install the OS vendor: Apple on macOS, Windows on Windows, Google on Linux."""
    with operation(lock=False) as store:
        os_vendor = {"Darwin": "apple", "Windows": "windows", "Linux": "google"}.get(
            platform.system()
        )
        with store.locked(exclusive=False):
            installed = store.installed()
        if os_vendor in installed:
            click.echo(f"📦 {os_vendor} is already installed.", err=True)
            return
        if installed:
            if os_vendor is None:
                click.echo("📦 Already set up: " + ", ".join(installed) + ".", err=True)
                return
            raise ValueError(
                "Other vendors are already installed. Run "
                f"emoji install --vendor {os_vendor} --use-as-default."
            )
        selected = [os_vendor] if os_vendor else pick_vendors(single=True)
        if not yes:
            if not sys.stdin.isatty():
                raise click.UsageError("Unattended setup requires --yes")
            click.confirm(
                f"📥 Install artwork for {selected[0]}?",
                default=False,
                abort=True,
                err=True,
            )
    ctx.invoke(
        install,
        vendor=tuple(selected),
        all_vendors=False,
        update=False,
        use_as_default=True,
    )


@cli.command()
@click.option("--vendor", multiple=True, required=True, type=click.Choice(VENDORS))
def uninstall(vendor: tuple[str, ...]) -> None:
    """Remove selected vendors without prompting; keep other installed artwork."""
    with operation(write=True) as store:
        failures = []
        for name in dict.fromkeys(vendor):
            try:
                was_default = store.default_vendor() == name
                removed, warnings = store.uninstall(name)
                if removed:
                    click.echo(f"📦 Removed {name}", err=True)
                    if was_default:
                        click.echo(
                            "⚙️ Default vendor cleared. Select an installed vendor with "
                            "emoji config set vendor VENDOR.",
                            err=True,
                        )
                else:
                    click.echo(
                        f"📦 {name} is not installed; nothing to remove.", err=True
                    )
                for warning in warnings:
                    click.echo(f"⚠️ {warning}", err=True)
            except (OSError, ValueError, KeyError, TypeError) as error:
                failures.append(name)
                click.echo(f"❌ {name}: {error}", err=True)
        if failures:
            raise ValueError("Uninstall failed for: " + ", ".join(failures))


@cli.group()
def config() -> None:
    """Save default vendor and skin-tone preferences."""


@config.group("set")
def config_set() -> None:
    """Set a default vendor or skin tone."""


def save_preference(key: str, value: str) -> None:
    with operation(write=True) as store:
        if key == "vendor":
            store.vendor(value)
        preferences = store.preferences()
        preferences[key] = value
        atomic_json(store.config, preferences)
        click.echo(f"⚙️ {key}: {value}", err=True)


@config_set.command("vendor")
@click.argument("value", type=click.Choice(VENDORS))
def config_vendor(value: str) -> None:
    """Choose an installed vendor as the default."""
    save_preference("vendor", value)


@config_set.command("skin-tone")
@click.argument("value", type=click.Choice(TONES))
def config_skin_tone(value: str) -> None:
    """Choose the default skin tone."""
    save_preference("skin-tone", value)


@config.command("unset")
@click.argument("key", type=click.Choice(("vendor", "skin-tone")))
def config_unset(key: str) -> None:
    with operation(write=True) as store:
        preferences = store.preferences()
        preferences.pop(key, None)
        atomic_json(store.config, preferences)
        click.echo(f"⚙️ Cleared {key}", err=True)


@config.command("show")
def config_show() -> None:
    with operation() as store:
        click.echo(f"vendor: {store.default_vendor() or '(unset)'}")
        click.echo(f"skin-tone: {store.preferences().get('skin-tone', 'none')}")


@cli.command("list")
@click.argument("query", default="")
@click.option("--vendor", type=click.Choice(VENDORS))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(("plain", "colon", "emoji")),
    help="List format (default: plain).",
)
@click.option(
    "--emoji", "with_emoji", is_flag=True, help="Shortcut for --format emoji."
)
@click.option(
    "--colon", "with_colon", is_flag=True, help="Shortcut for --format colon."
)
def list_aliases(
    query: str,
    vendor: str | None,
    output_format: str | None,
    with_emoji: bool,
    with_colon: bool,
) -> None:
    """List available shortcodes matching an alias or emoji name."""
    formats = {
        value
        for value in (
            output_format,
            "emoji" if with_emoji else None,
            "colon" if with_colon else None,
        )
        if value is not None
    }
    if len(formats) > 1:
        raise click.UsageError("Choose one list format: plain, colon, or emoji")
    selected_format = next(iter(formats), "plain")
    with operation() as store:
        index, records = store.collection(store.vendor(vendor))
        query = query.casefold()
        for alias, key in sorted(index["aliases"].items()):
            entry = index["entries"][key]
            if key in records and any(
                query in text.casefold()
                for text in (alias, entry["name"], entry["cldr_name"])
            ):
                if selected_format == "colon":
                    click.echo(f":{alias}:")
                elif selected_format == "emoji":
                    # Convert hyphen-separated hex code points into Unicode characters.
                    emoji = "".join(chr(int(point, 16)) for point in key.split("-"))
                    click.echo(f"{emoji} {alias}")
                else:
                    click.echo(alias)


@cli.command()
def status() -> None:
    """Show installed resource versions and the saved default vendor."""
    with operation() as store:
        installed = store.installed()
        if not installed:
            click.echo(
                "No vendors installed. Run emoji install --vendor apple.", err=True
            )
        for vendor, installation in installed.items():
            default = " (default)" if vendor == store.default_vendor() else ""
            click.echo(f"{vendor}: {installation['release']}{default}")


if __name__ == "__main__":
    cli()
