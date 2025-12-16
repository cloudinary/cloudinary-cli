import os
from datetime import datetime, timezone

import click
import cloudinary

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.config_utils import get_cloudinary_config, config_to_dict
from cloudinary_cli.utils.json_utils import print_json, read_json_from_file, write_json_to_file
from cloudinary_cli.modules.settings.utils.pick import parse_picks
from cloudinary_cli.utils.utils import confirm_action, normalize_list_params, print_help_and_exit

from .store import (
    get_settings_store_bundle_path,
    list_settings_store_entries,
    delete_settings_store_bundle,
    ensure_settings_store_dirs,
    resolve_cloud_name_or_current,
)
from .providers.smd import (
    export_smd_bundle,
    apply_smd_bundle,
    delete_smd_items,
    summarize_smd_bundle,
    render_smd_fields_table,
)


SUPPORTED_TYPES = ("smd",)
DEFAULT_TYPES = ("smd",)


@click.group("settings",
             short_help="Save/restore settings bundles, or clone settings between accounts.",
             help="""
\b
Save and restore Cloudinary settings bundles, and optionally clone settings from the current account to other accounts.

Settings bundles are stored under your Cloudinary CLI config folder, namespaced by cloud name:
  ~/.cloudinary-cli/settings/<cloud_name>/<bundle_name>.json

You can also export/import using explicit file paths via --out / --in.
""")
def settings():
    ensure_settings_store_dirs()
    return True


@settings.group("smd", short_help="Structured Metadata (SMD) helpers.")
def settings_smd():
    return True


@settings_smd.command("delete", short_help="Delete selected SMD fields/rules from the current account.")
@click.option("--pick", "picks", multiple=True, nargs=3,
              help="Select items to delete. Repeatable. Format: --pick <group> <kind> <value>. "
                   "Examples: --pick smd field content_status --pick smd rule \"My rule\". "
                   "Use --pick smd field all / --pick smd rule all to select all.")
@click.option("--smd-include-rules", is_flag=True, default=False,
              help="When picking SMD fields, also delete rules that reference those fields.")
@click.option("--dry-run", is_flag=True, default=False, help="Plan and report deletions without applying.")
@click.option("-F", "--force", is_flag=True, help="Skip confirmation prompts.")
def smd_delete(picks, smd_include_rules, dry_run, force):
    if picks:
        picked_types, smd_fields, smd_rules = parse_picks(picks)
        if picked_types and "smd" not in picked_types:
            raise click.UsageError("Unsupported pick group(s) for this command. Use --pick smd ...")
    else:
        # No picks => delete all SMD fields + rules (still confirmed unless -F).
        smd_fields = ["__ALL__"]
        smd_rules = ["__ALL__"]

    return delete_smd_items(
        target_options=None,
        dry_run=dry_run,
        force=force,
        field_external_ids=normalize_list_params(smd_fields) if smd_fields else None,
        rule_names=normalize_list_params(smd_rules) if smd_rules else None,
        include_related_rules=smd_include_rules,
    )


@settings.command("folder", short_help="Show (and optionally open) the settings store folder.")
@click.option("--open", "open_folder", is_flag=True, default=False,
              help="Open the settings folder in your OS file browser.")
def settings_folder(open_folder):
    folder = ensure_settings_store_dirs()
    click.echo(folder)
    if open_folder:
        # click.launch opens a path/URL with the default OS handler (Finder/Explorer/etc.).
        click.launch(folder)
    return True


@settings.command("save", short_help="Save settings bundle to the local settings store.")
@click.argument("name", required=False)
@click.option("-t", "--types", multiple=True,
              help=f"Settings types to save. Supported: {', '.join(SUPPORTED_TYPES)}. Default: {', '.join(DEFAULT_TYPES)}.")
@click.option("--pick", "picks", multiple=True, nargs=3,
              help="Select specific items to include. Repeatable. Format: --pick <group> <kind> <value>. "
                   "Examples: --pick smd field content_status --pick smd rule \"My rule\"")
@click.option("--smd-include-rules", is_flag=True, default=False,
              help="When picking SMD fields, also include rules that reference those fields (and any required fields).")
@click.option("--out", "out_file", help="Write bundle to an explicit file path (file-only; does not save to the settings store).")
@click.option("-F", "--force", is_flag=True, help="Overwrite existing saved bundle without prompting.")
def save_settings(name, types, picks, smd_include_rules, out_file, force):
    picked_types, smd_fields, smd_rules = parse_picks(picks)
    selected_types = normalize_list_params(types) if types else (picked_types or list(DEFAULT_TYPES))
    unknown = sorted(set(selected_types) - set(SUPPORTED_TYPES))
    if unknown:
        raise click.UsageError(f"Unsupported type(s): {', '.join(unknown)}. Supported: {', '.join(SUPPORTED_TYPES)}")

    cloud_name = cloudinary.config().cloud_name
    if not cloud_name:
        logger.error("No Cloudinary configuration found.")
        return False

    if not name and not force:
        # Interactive convenience: prompt for a name (blank => timestamp).
        try:
            if click.get_text_stream('stdin').isatty():
                name = click.prompt("Bundle name (leave blank for timestamp)", default="", show_default=False)
        except Exception:
            pass

    if not name:
        # Filesystem-safe, readable timestamp (local time, ms precision)
        now = datetime.now().astimezone()
        name = now.strftime("%Y-%m-%d_%H-%M-%S-") + f"{int(now.microsecond / 1000):03d}"

    created_at = datetime.now(timezone.utc).isoformat()
    bundle = {
        "schema_version": 1,
        "name": name,
        "created_at": created_at,
        "source": {"cloud_name": cloud_name},
        "types": selected_types,
    }

    if "smd" in selected_types:
        bundle["smd"] = export_smd_bundle(
            field_external_ids=normalize_list_params(smd_fields) if smd_fields else None,
            rule_names=normalize_list_params(smd_rules) if smd_rules else None,
            include_related_rules=smd_include_rules,
        )
        field_rows, rules = summarize_smd_bundle(bundle["smd"])
        click.echo("SMD:")
        click.echo(f"  fields ({len(field_rows)}):")
        if field_rows:
            for line in render_smd_fields_table(field_rows, max_total=120):
                click.echo(line)
        click.echo(f"  rules ({len(rules)}):")
        for rn in rules:
            click.echo(f"    - {rn}")

    if out_file:
        if os.path.exists(out_file) and not force:
            if not confirm_action(f"File '{out_file}' already exists. Overwrite? (y/N)"):
                logger.info("Stopping.")
                return False
        # File-only mode: always pretty-print for readability and diffs.
        write_json_to_file(bundle, out_file, indent=2)
        logger.info(f"Exported bundle to '{out_file}'.")
        return True

    bundle_path = get_settings_store_bundle_path(cloud_name, name)
    if os.path.exists(bundle_path) and not force:
        if not confirm_action(f"Settings bundle '{name}' already exists for cloud '{cloud_name}'. Overwrite? (y/N)"):
            logger.info("Stopping.")
            return False

    # Store mode: always pretty-print for readability and diffs.
    write_json_to_file(bundle, bundle_path, indent=2)

    logger.info(f"Saved settings bundle '{name}' for cloud '{cloud_name}'.")
    return True


@settings.command("ls", short_help="List saved settings bundles.")
@click.option("--cloud", "cloud_name", help="Filter by cloud name (defaults to all clouds).")
@click.option("--json", "as_json", is_flag=True, default=False, help="Print output as JSON.")
def list_settings(cloud_name, as_json):
    entries = list_settings_store_entries(cloud_name=cloud_name)
    if as_json:
        print_json(entries)
        return True

    if not entries:
        logger.info("No saved settings bundles found.")
        return True

    # Simple stable, grep-friendly output
    for e in entries:
        click.echo(f"{e['cloud_name']}\t{e['name']}")
    return True


@settings.command("show", short_help="Show a saved settings bundle.")
@click.argument("name")
@click.option("--cloud", "cloud_name", help="Cloud name namespace. Default: current cloud.")
@click.option("--out", "out_file", help="Write bundle to an explicit file path.")
def show_settings(name, cloud_name, out_file):
    cloud_name = resolve_cloud_name_or_current(cloud_name)
    bundle_path = get_settings_store_bundle_path(cloud_name, name)
    if not os.path.exists(bundle_path):
        logger.error(f"Settings bundle '{name}' not found for cloud '{cloud_name}'.")
        return False

    bundle = read_json_from_file(bundle_path)
    if out_file:
        write_json_to_file(bundle, out_file, indent=2)
    print_json(bundle)
    return True


@settings.command("rm", short_help="Delete a saved settings bundle.")
@click.argument("name")
@click.option("--cloud", "cloud_name", help="Cloud name namespace. Default: current cloud.")
@click.option("-F", "--force", is_flag=True, help="Delete without prompting.")
def rm_settings(name, cloud_name, force):
    cloud_name = resolve_cloud_name_or_current(cloud_name)
    if not force:
        if not confirm_action(f"Delete settings bundle '{name}' for cloud '{cloud_name}'? (y/N)"):
            logger.info("Stopping.")
            return False

    deleted = delete_settings_store_bundle(cloud_name, name)
    if not deleted:
        logger.error(f"Settings bundle '{name}' not found for cloud '{cloud_name}'.")
        return False

    logger.info(f"Deleted settings bundle '{name}' for cloud '{cloud_name}'.")
    return True


@settings.command("restore", short_help="Restore settings to the current account.")
@click.argument("name", required=False)
@click.option("--cloud", "cloud_name", help="Cloud name namespace for saved bundles. Default: current cloud.")
@click.option("--in", "in_file", help="Restore from an explicit file path instead of the settings store.")
@click.option("-t", "--types", multiple=True,
              help=f"Settings types to restore. Supported: {', '.join(SUPPORTED_TYPES)}. Default: types present in bundle.")
@click.option("--pick", "picks", multiple=True, nargs=3,
              help="Select specific items to apply. Repeatable. Format: --pick <group> <kind> <value>.")
@click.option("--smd-include-rules", is_flag=True, default=False,
              help="When picking SMD fields, also apply rules that reference those fields (and any required fields).")
@click.option("--mode", type=click.Choice(["create-missing", "upsert", "sync"], case_sensitive=False), default="create-missing",
              help="How to apply settings: create-missing, upsert (create+update), or sync (create+update+delete extras).")
@click.option("--dry-run", is_flag=True, default=False, help="Plan and report changes without applying.")
@click.option("-F", "--force", is_flag=True, help="Skip confirmation prompts.")
def restore_settings(name, cloud_name, in_file, types, picks, smd_include_rules, mode, dry_run, force):
    picked_types, smd_fields, smd_rules = parse_picks(picks)
    if not name and not in_file:
        # Interactive convenience: prompt user to pick from store.
        # In non-interactive environments, keep the old strict behavior.
        try:
            is_tty = click.get_text_stream('stdin').isatty()
        except Exception:
            is_tty = False

        if not is_tty:
            print_help_and_exit()

        cloud_name = resolve_cloud_name_or_current(cloud_name)
        entries = list_settings_store_entries(cloud_name=cloud_name)
        if not entries:
            logger.info(f"No saved settings bundles found for cloud '{cloud_name}'.")
            return False

        click.echo(f"Saved settings bundles for '{cloud_name}':")
        for i, e in enumerate(entries, start=1):
            click.echo(f"{i}. {e['name']}")

        idx = click.prompt("Select bundle number", type=int, default=1)
        if idx < 1 or idx > len(entries):
            raise click.UsageError(f"Invalid selection: {idx}. Please choose a number between 1 and {len(entries)}.")
        name = entries[idx - 1]["name"]

    if in_file:
        bundle = read_json_from_file(in_file)
    else:
        cloud_name = resolve_cloud_name_or_current(cloud_name)
        bundle_path = get_settings_store_bundle_path(cloud_name, name)
        if not os.path.exists(bundle_path):
            logger.error(f"Settings bundle '{name}' not found for cloud '{cloud_name}'.")
            return False
        bundle = read_json_from_file(bundle_path)

    selected_types = normalize_list_params(types) if types else (picked_types or bundle.get("types", list(DEFAULT_TYPES)))
    unknown = sorted(set(selected_types) - set(SUPPORTED_TYPES))
    if unknown:
        raise click.UsageError(f"Unsupported type(s): {', '.join(unknown)}. Supported: {', '.join(SUPPORTED_TYPES)}")

    if "smd" in selected_types and bundle.get("smd"):
        return apply_smd_bundle(
            bundle["smd"],
            target_options=None,
            dry_run=dry_run,
            force=force,
            field_external_ids=normalize_list_params(smd_fields) if smd_fields else None,
            rule_names=normalize_list_params(smd_rules) if smd_rules else None,
            include_related_rules=smd_include_rules,
            mode=mode,
        )

    logger.info("Nothing to restore (no supported types found in bundle).")
    return True


@settings.command("clone", short_help="Clone settings from current account or a bundle to one or more target accounts.")
@click.argument("targets", nargs=-1)
@click.option("--from", "from_name", help="Use a saved settings bundle name instead of exporting from current account.")
@click.option("--cloud", "cloud_name", help="Cloud name namespace for --from bundles. Default: current cloud.")
@click.option("--in", "in_file", help="Use an explicit bundle file path instead of exporting from current account.")
@click.option("--out", "out_file", help="Also write the source bundle to an explicit file path.")
@click.option("-t", "--types", multiple=True,
              help=f"Settings types to clone. Supported: {', '.join(SUPPORTED_TYPES)}. Default: {', '.join(DEFAULT_TYPES)}.")
@click.option("--pick", "picks", multiple=True, nargs=3,
              help="Select specific items to clone/apply. Repeatable. Format: --pick <group> <kind> <value>.")
@click.option("--smd-include-rules", is_flag=True, default=False,
              help="When picking SMD fields, also apply rules that reference those fields (and any required fields).")
@click.option("--mode", type=click.Choice(["create-missing", "upsert", "sync"], case_sensitive=False), default="create-missing",
              help="How to apply settings: create-missing, upsert (create+update), or sync (create+update+delete extras).")
@click.option("--dry-run", is_flag=True, default=False, help="Plan and report changes without applying.")
@click.option("-F", "--force", is_flag=True, help="Skip confirmation prompts.")
def clone_settings(targets, from_name, cloud_name, in_file, out_file, types, picks, smd_include_rules, mode, dry_run, force):
    picked_types, smd_fields, smd_rules = parse_picks(picks)
    if not targets:
        raise click.UsageError("Please provide one or more target configs (CLOUDINARY_URL or saved config name).")

    if in_file and from_name:
        raise click.UsageError("Please use only one of --in or --from.")

    # Resolve / build source bundle
    if in_file:
        bundle = read_json_from_file(in_file)
    elif from_name:
        cloud_name = resolve_cloud_name_or_current(cloud_name)
        bundle_path = get_settings_store_bundle_path(cloud_name, from_name)
        if not os.path.exists(bundle_path):
            logger.error(f"Settings bundle '{from_name}' not found for cloud '{cloud_name}'.")
            return False
        bundle = read_json_from_file(bundle_path)
    else:
        selected_types = normalize_list_params(types) if types else (picked_types or list(DEFAULT_TYPES))
        unknown = sorted(set(selected_types) - set(SUPPORTED_TYPES))
        if unknown:
            raise click.UsageError(f"Unsupported type(s): {', '.join(unknown)}. Supported: {', '.join(SUPPORTED_TYPES)}")

        cloud_name_src = cloudinary.config().cloud_name
        if not cloud_name_src:
            logger.error("No Cloudinary configuration found.")
            return False

        bundle = {
            "schema_version": 1,
            "name": "(ad-hoc)",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": {"cloud_name": cloud_name_src},
            "types": selected_types,
        }
        if "smd" in selected_types:
            bundle["smd"] = export_smd_bundle(
                field_external_ids=normalize_list_params(smd_fields) if smd_fields else None,
                rule_names=normalize_list_params(smd_rules) if smd_rules else None,
                include_related_rules=smd_include_rules,
            )

    if out_file:
        write_json_to_file(bundle, out_file, indent=2)

    # Apply to all targets
    ok = True
    for target in targets:
        target_config = get_cloudinary_config(target)
        if not target_config:
            ok = False
            continue
        target_options = config_to_dict(target_config)
        target_cloud = target_options.get("cloud_name", target)
        logger.info(f"Cloning settings to '{target_cloud}'...")

        effective_types = normalize_list_params(types) if types else (picked_types or bundle.get("types", list(DEFAULT_TYPES)))
        if bundle.get("smd") and "smd" in effective_types:
            res = apply_smd_bundle(
                bundle["smd"],
                target_options=target_options,
                dry_run=dry_run,
                force=force,
                field_external_ids=normalize_list_params(smd_fields) if smd_fields else None,
                rule_names=normalize_list_params(smd_rules) if smd_rules else None,
                include_related_rules=smd_include_rules,
                mode=mode,
            )
            ok = ok and bool(res)

    return ok
