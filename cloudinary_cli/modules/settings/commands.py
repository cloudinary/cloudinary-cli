import logging
import os
from datetime import datetime, timezone

import click
import cloudinary

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.config_utils import get_cloudinary_config, config_to_dict
from cloudinary_cli.utils.json_utils import print_json, read_json_from_file, write_json_to_file
from cloudinary_cli.utils.utils import confirm_action, normalize_list_params, print_help_and_exit

from .providers import (
    PROVIDERS,
    APPLY_ORDER,
    ALL_COMPONENTS,
    DEFAULT_COMPONENTS,
    list_components_status,
)
from .providers.smd import (
    apply_smd_bundle,
    delete_smd_items,
    export_smd_bundle,
    summarize_smd_bundle,
    render_smd_fields_table,
)
from .providers.transformations import (
    apply_transformations_snapshot,
    delete_transformations,
    export_transformations_snapshot,
    summarize_transformations_snapshot,
    PICK_ALL_SENTINEL as TRANSFORMATIONS_PICK_ALL_SENTINEL,
)
from .providers.upload_presets import (
    apply_upload_presets,
    delete_upload_presets,
    export_upload_presets,
    summarize_upload_presets,
    PICK_ALL_SENTINEL as UPLOAD_PRESETS_PICK_ALL_SENTINEL,
)
from .providers.streaming_profiles import (
    apply_streaming_profiles,
    delete_streaming_profiles,
    export_streaming_profiles,
    summarize_streaming_profiles,
    PICK_ALL_SENTINEL as STREAMING_PROFILES_PICK_ALL_SENTINEL,
)
from .providers.upload_mappings import (
    apply_upload_mappings,
    delete_upload_mappings,
    export_upload_mappings,
    summarize_upload_mappings,
    PICK_ALL_SENTINEL as UPLOAD_MAPPINGS_PICK_ALL_SENTINEL,
)
from .providers.config import (
    diff_config_bundle,
    export_config_bundle,
    summarize_config_bundle,
)
from .store import (
    get_settings_store_snapshot_path,
    list_settings_store_entries,
    delete_settings_store_snapshot,
    ensure_settings_store_dirs,
    resolve_cloud_name_or_current,
)
from .utils.dirstore import read_snapshot_dir, write_snapshot_dir
from .utils.envelope import (
    SCHEMA_VERSION,
    finalize_envelope,
    load_snapshot,
    make_envelope,
)
from .utils.pick import parse_picks, SMD_PICK_ALL_SENTINEL
from .utils.render import c, diff_any


SUPPORTED_COMPONENTS = ALL_COMPONENTS                # backwards-compat alias


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("settings",
             short_help="Save/restore settings snapshots, or clone settings between accounts.",
             help="""
\b
Save and restore Cloudinary settings snapshots, and optionally clone settings from the current account to other accounts.

Settings snapshots are stored under your Cloudinary CLI config folder, namespaced by cloud name:
  ~/.cloudinary-cli/settings/<cloud_name>/<snapshot_name>.json

You can also export/import using explicit file paths via --out / --in, or per-component
directory layouts via --out-dir / --in-dir.
""")
def settings():
    ensure_settings_store_dirs()
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_components(components):
    unknown = sorted(set(components) - set(ALL_COMPONENTS))
    if unknown:
        raise click.UsageError(
            f"Unsupported component(s): {', '.join(unknown)}. "
            f"Supported: {', '.join(ALL_COMPONENTS)}"
        )


def _list_or_none(values):
    return normalize_list_params(values) if values else None


def _is_all(values, sentinels):
    return values and any(v in sentinels for v in values)


def _trans_filters(transformation_names):
    if not transformation_names:
        return None
    if _is_all(transformation_names, (TRANSFORMATIONS_PICK_ALL_SENTINEL,)):
        return None
    return normalize_list_params(transformation_names)


def _preset_filters(preset_names):
    if not preset_names:
        return None
    if _is_all(preset_names, (UPLOAD_PRESETS_PICK_ALL_SENTINEL,)):
        return None
    return normalize_list_params(preset_names)


def _profile_filters(profile_names):
    if not profile_names:
        return None
    if _is_all(profile_names, (STREAMING_PROFILES_PICK_ALL_SENTINEL,)):
        return None
    return normalize_list_params(profile_names)


def _mapping_filters(folders):
    if not folders:
        return None
    if _is_all(folders, (UPLOAD_MAPPINGS_PICK_ALL_SENTINEL,)):
        return None
    return normalize_list_params(folders)


def _selection_record(selected_components, picks):
    """Persist the user's exact --component / --pick choices into the envelope."""
    return {
        "components": list(selected_components),
        "picks": [list(p) for p in (picks or [])],
    }


def _components_label(selected_components):
    if set(selected_components) == set(ALL_COMPONENTS):
        return "all"
    return "-".join(selected_components)


def _read_snapshot(in_file=None, in_dir=None, name=None, cloud_name=None):
    """
    Resolve a snapshot from one of: explicit file (--in), directory (--in-dir),
    or named entry in the local store (name + cloud_name).
    """
    if in_dir:
        snap = read_snapshot_dir(in_dir, ALL_COMPONENTS)
        return load_snapshot(snap)
    if in_file:
        return load_snapshot(read_json_from_file(in_file))
    cloud_name = resolve_cloud_name_or_current(cloud_name)
    snapshot_path = get_settings_store_snapshot_path(cloud_name, name)
    if not os.path.exists(snapshot_path):
        logger.error(f"Settings snapshot '{name}' not found for cloud '{cloud_name}'.")
        return None
    return load_snapshot(read_json_from_file(snapshot_path))


def _print_per_component_summary(snapshot):
    """Pretty per-component summaries used by save/show."""
    if "smd" in snapshot and snapshot["smd"]:
        field_rows, rules = summarize_smd_bundle(snapshot["smd"])
        click.echo("SMD:")
        click.echo(f"  fields ({len(field_rows)}):")
        if field_rows:
            for line in render_smd_fields_table(field_rows, max_total=120):
                click.echo(line)
        click.echo(f"  rules ({len(rules)}):")
        for rn in rules:
            click.echo(f"    - {rn}")

    if "transformations" in snapshot and snapshot["transformations"]:
        names = summarize_transformations_snapshot(snapshot["transformations"])
        click.echo(f"Transformations ({len(names)}):")
        for n in names:
            click.echo(f"  - {n}")

    if "upload_presets" in snapshot and snapshot["upload_presets"]:
        names = summarize_upload_presets(snapshot["upload_presets"])
        click.echo(f"Upload presets ({len(names)}):")
        for n in names:
            click.echo(f"  - {n}")

    if "streaming_profiles" in snapshot and snapshot["streaming_profiles"]:
        items = summarize_streaming_profiles(snapshot["streaming_profiles"])
        click.echo(f"Streaming profiles ({len(items)}):")
        for n in items:
            click.echo(f"  - {n}")

    if "upload_mappings" in snapshot and snapshot["upload_mappings"]:
        names = summarize_upload_mappings(snapshot["upload_mappings"])
        click.echo(f"Upload mappings ({len(names)}):")
        for n in names:
            click.echo(f"  - {n}")

    if "config" in snapshot and snapshot["config"]:
        lines = summarize_config_bundle(snapshot["config"])
        click.echo(f"Config (read-only, {len(lines)} field(s)):")
        for ln in lines:
            click.echo(f"  - {ln}")


# ---------------------------------------------------------------------------
# Per-component admin subgroups
# ---------------------------------------------------------------------------

@settings.group("smd", short_help="Structured Metadata (SMD) helpers.")
def settings_smd():
    return True


@settings_smd.command("delete", short_help="Delete selected SMD fields/rules from the current account.")
@click.option("--pick", "picks", multiple=True, nargs=3,
              help="Select items to delete. Repeatable. Format: --pick <group> <kind> <value>.")
@click.option("--smd-include-rules", is_flag=True, default=False,
              help="When picking SMD fields, also delete rules that reference those fields.")
@click.option("--dry-run", is_flag=True, default=False, help="Plan and report deletions without applying.")
@click.option("-F", "--force", is_flag=True, help="Skip confirmation prompts.")
def smd_delete(picks, smd_include_rules, dry_run, force):
    parsed = parse_picks(picks)
    picked_components = parsed.selected_components
    smd_fields = list(parsed.smd_fields or [])
    smd_rules = list(parsed.smd_rules or [])

    if picked_components and "smd" not in picked_components:
        raise click.UsageError("Unsupported pick group(s) for this command. Use --pick smd ...")

    if not smd_fields and not smd_rules:
        smd_fields = [SMD_PICK_ALL_SENTINEL]
        smd_rules = [SMD_PICK_ALL_SENTINEL]

    return delete_smd_items(
        target_options=None,
        dry_run=dry_run,
        force=force,
        field_external_ids=_list_or_none(smd_fields),
        rule_names=_list_or_none(smd_rules),
        include_related_rules=smd_include_rules,
    )


@settings.group("transformations", short_help="Named transformations helpers.")
def settings_transformations():
    return True


@settings_transformations.command("delete", short_help="Delete selected named transformations.")
@click.argument("names", nargs=-1)
@click.option("--pick", "picks", multiple=True, nargs=3,
              help="Select transformations to delete (repeatable).")
@click.option("--dry-run", is_flag=True, default=False)
@click.option("-F", "--force", is_flag=True, help="Skip confirmation prompts.")
def transformations_delete(names, picks, dry_run, force):
    parsed = parse_picks(picks)
    pick_names = parsed.transformation_names or []
    selected = list(names) + list(pick_names)
    if not selected:
        raise click.UsageError("Please provide at least one transformation name (or use --pick / '*').")

    return delete_transformations(
        target_options=None,
        dry_run=dry_run,
        force=force,
        transformation_names=selected,
    )


@settings.group("upload-presets", short_help="Upload preset helpers.")
def settings_upload_presets():
    return True


@settings_upload_presets.command("delete", short_help="Delete selected upload presets.")
@click.argument("names", nargs=-1)
@click.option("--pick", "picks", multiple=True, nargs=3)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("-F", "--force", is_flag=True, help="Skip confirmation prompts.")
def upload_presets_delete(names, picks, dry_run, force):
    parsed = parse_picks(picks)
    pick_names = parsed.upload_preset_names or []
    selected = list(names) + list(pick_names)
    if not selected:
        raise click.UsageError("Please provide at least one preset name (or use --pick / '*').")

    return delete_upload_presets(
        target_options=None,
        dry_run=dry_run,
        force=force,
        preset_names=selected,
    )


@settings.group("streaming-profiles", short_help="Streaming profile helpers.")
def settings_streaming_profiles():
    return True


@settings_streaming_profiles.command("delete", short_help="Delete custom streaming profiles (or revert built-ins with explicit opt-in).")
@click.argument("names", nargs=-1)
@click.option("--pick", "picks", multiple=True, nargs=3)
@click.option("--allow-revert-builtins", is_flag=True, default=False,
              help="Allow DELETE on built-in profiles (reverts overrides). See settings-design.md §6.4.")
@click.option("--dry-run", is_flag=True, default=False)
@click.option("-F", "--force", is_flag=True, help="Skip confirmation prompts.")
def streaming_profiles_delete(names, picks, allow_revert_builtins, dry_run, force):
    parsed = parse_picks(picks)
    pick_names = parsed.streaming_profile_names or []
    selected = list(names) + list(pick_names)
    if not selected:
        raise click.UsageError("Please provide at least one profile name (or use --pick / '*').")

    return delete_streaming_profiles(
        target_options=None,
        dry_run=dry_run,
        force=force,
        profile_names=selected,
        allow_revert_builtins=allow_revert_builtins,
    )


@settings.group("upload-mappings", short_help="Upload mapping helpers.")
def settings_upload_mappings():
    return True


@settings_upload_mappings.command("delete", short_help="Delete selected upload mappings.")
@click.argument("folders", nargs=-1)
@click.option("--pick", "picks", multiple=True, nargs=3)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("-F", "--force", is_flag=True, help="Skip confirmation prompts.")
def upload_mappings_delete(folders, picks, dry_run, force):
    parsed = parse_picks(picks)
    pick_names = parsed.upload_mapping_folders or []
    selected = list(folders) + list(pick_names)
    if not selected:
        raise click.UsageError("Please provide at least one folder (or use --pick / '*').")

    return delete_upload_mappings(
        target_options=None,
        dry_run=dry_run,
        force=force,
        folders=selected,
    )


@settings.group("config", short_help="Product environment config helpers (read/diff only).")
def settings_config():
    return True


@settings_config.command("diff", short_help="Show drift between a snapshot's captured config and the current account.")
@click.argument("name", required=False)
@click.option("--cloud", "cloud_name", help="Cloud name namespace for saved snapshots.")
@click.option("--in", "in_file", help="Diff a snapshot file path instead of the store.")
@click.option("--in-dir", "in_dir", help="Diff a snapshot directory.")
def settings_config_diff(name, cloud_name, in_file, in_dir):
    """Alias of `cld settings diff --component config`."""
    return _run_diff(name, cloud_name, in_file, in_dir, components=("config",), picks=())


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------

@settings.command("folder", short_help="Show (and optionally open) the settings store folder.")
@click.option("--open", "open_folder", is_flag=True, default=False)
def settings_folder(open_folder):
    folder = ensure_settings_store_dirs()
    click.echo(folder)
    if open_folder:
        click.launch(folder)
    return True


@settings.command("components", short_help="List supported components, identity fields, and apply status.")
@click.option("--json", "as_json", is_flag=True, default=False)
def settings_components(as_json):
    rows = list_components_status()
    if as_json:
        print_json(rows)
        return True
    click.echo(f"{'component'.ljust(20)} {'pick kinds'.ljust(20)} {'delete'.ljust(8)} apply")
    for r in rows:
        click.echo(
            f"{r['component'].ljust(20)} "
            f"{(','.join(r['pick_kinds']) or '-').ljust(20)} "
            f"{('yes' if r['supports_delete'] else 'no').ljust(8)} "
            f"{'yes' if r['applicable'] else 'no (read-only)'}"
        )
    return True


@settings.command("save", short_help="Save settings snapshot to the local settings store.")
@click.argument("name", required=False)
@click.option("--component", "components", multiple=True,
              help=f"Components to save. Supported: {', '.join(ALL_COMPONENTS)}.")
@click.option("--pick", "picks", multiple=True, nargs=3,
              help="Select specific items. Repeatable. Format: --pick <group> <kind> <value>.")
@click.option("--smd-include-rules", is_flag=True, default=False)
@click.option("--out", "out_file", help="Write snapshot to a file path (single-file mode).")
@click.option("--out-dir", "out_dir", help="Write snapshot as a per-component directory layout.")
@click.option("--note", "note", default=None, help="Free-form note recorded in metadata.")
@click.option("--tag", "tags", multiple=True, help="Tag for ls --tag filtering. Repeatable.")
@click.option("-F", "--force", is_flag=True, help="Overwrite existing snapshot without prompting.")
def save_settings(name, components, picks, smd_include_rules, out_file, out_dir, note, tags, force):
    if out_file and out_dir:
        raise click.UsageError("Use only one of --out or --out-dir.")

    parsed = parse_picks(picks)
    picked_components = parsed.selected_components

    selected_components = (
        normalize_list_params(components) if components
        else (picked_components or list(DEFAULT_COMPONENTS))
    )
    _validate_components(selected_components)

    cloud_name = cloudinary.config().cloud_name
    if not cloud_name:
        logger.error("No Cloudinary configuration found.")
        return False

    components_label = _components_label(selected_components)
    now = datetime.now().astimezone()
    default_name = f"{cloud_name}_{components_label}_" + now.strftime("%Y-%m-%d_%H-%M-%S-") + f"{int(now.microsecond / 1000):03d}"

    if not name and not force and not out_file and not out_dir:
        try:
            if click.get_text_stream('stdin').isatty():
                name = click.prompt("Snapshot name", default=default_name, show_default=True)
        except Exception:
            pass

    if not name:
        now = datetime.now().astimezone()
        name = f"{cloud_name}_{components_label}_" + now.strftime("%Y-%m-%d_%H-%M-%S-") + f"{int(now.microsecond / 1000):03d}"

    target_path = None
    if not (out_file or out_dir):
        target_path = get_settings_store_snapshot_path(cloud_name, name)

    snapshot = make_envelope(
        name=name,
        cloud_name=cloud_name,
        components=selected_components,
        selection=_selection_record(selected_components, picks),
        metadata={"notes": note, "tags": list(tags or [])},
    )

    # Component bundles.
    if "smd" in selected_components:
        snapshot["smd"] = export_smd_bundle(
            field_external_ids=_list_or_none(parsed.smd_fields),
            rule_names=_list_or_none(parsed.smd_rules),
            include_related_rules=smd_include_rules,
        )

    if "transformations" in selected_components:
        snapshot["transformations"] = export_transformations_snapshot(
            transformation_names=_trans_filters(parsed.transformation_names),
        )

    if "upload_presets" in selected_components:
        snapshot["upload_presets"] = export_upload_presets(
            preset_names=_preset_filters(parsed.upload_preset_names),
        )

    if "streaming_profiles" in selected_components:
        snapshot["streaming_profiles"] = export_streaming_profiles(
            profile_names=_profile_filters(parsed.streaming_profile_names),
        )

    if "upload_mappings" in selected_components:
        snapshot["upload_mappings"] = export_upload_mappings(
            folders=_mapping_filters(parsed.upload_mapping_folders),
        )

    if "config" in selected_components:
        snapshot["config"] = export_config_bundle()
        # Mirror folder_mode etc. into source.config_settings for convenience.
        cfg_settings = (snapshot["config"].get("settings") or {}).get("settings") or {}
        if cfg_settings:
            snapshot["source"]["config_settings"] = cfg_settings

    # Display per-component summary.
    _print_per_component_summary(snapshot)

    # Fingerprints + checksum.
    finalize_envelope(snapshot, ALL_COMPONENTS)

    if out_dir:
        if os.path.exists(out_dir) and os.listdir(out_dir) and not force:
            if not confirm_action(f"Directory '{out_dir}' is not empty. Overwrite component files? (y/N)"):
                logger.info("Stopping.")
                return False
        write_snapshot_dir(out_dir, snapshot, ALL_COMPONENTS)
        logger.info(f"Exported snapshot to directory '{out_dir}'.")
        return True

    if out_file:
        if os.path.exists(out_file) and not force:
            if not confirm_action(f"File '{out_file}' already exists. Overwrite? (y/N)"):
                logger.info("Stopping.")
                return False
        write_json_to_file(snapshot, out_file, indent=2)
        logger.info(f"Exported snapshot to '{out_file}'.")
        return True

    if os.path.exists(target_path) and not force:
        if not confirm_action(f"Settings snapshot '{name}' already exists for cloud '{cloud_name}'. Overwrite? (y/N)"):
            logger.info("Stopping.")
            return False

    write_json_to_file(snapshot, target_path, indent=2)
    logger.info(f"Saved settings snapshot '{name}' for cloud '{cloud_name}'.")
    return True


@settings.command("ls", short_help="List saved settings snapshots.")
@click.option("--cloud", "cloud_name", help="Filter by cloud name (defaults to all clouds).")
@click.option("--json", "as_json", is_flag=True, default=False)
@click.option("--tag", "filter_tags", multiple=True, help="Show only snapshots with these tags (AND).")
def list_settings(cloud_name, as_json, filter_tags):
    entries = list_settings_store_entries(cloud_name=cloud_name)
    if filter_tags or as_json:
        # Enrich entries with snapshot metadata.
        filter_tags = list(filter_tags or [])
        enriched = []
        for e in entries:
            try:
                snap = read_json_from_file(e["path"])
            except Exception:
                snap = {}
            tags = ((snap.get("metadata") or {}).get("tags")) or []
            cloud = (snap.get("source") or {}).get("cloud_name")
            row = {
                "cloud_name": e["cloud_name"],
                "name": e["name"],
                "path": e["path"],
                "schema_version": snap.get("schema_version"),
                "created_at": snap.get("created_at"),
                "tags": tags,
                "notes": (snap.get("metadata") or {}).get("notes"),
                "snapshot_cloud_name": cloud,
            }
            if filter_tags and not all(t in tags for t in filter_tags):
                continue
            enriched.append(row)
        if as_json:
            print_json(enriched)
            return True
        if not enriched:
            logger.info("No matching settings snapshots.")
            return True
        for r in enriched:
            tag_str = (",".join(r["tags"]) if r["tags"] else "-")
            click.echo(f"{r['cloud_name']}\t{r['name']}\t{tag_str}")
        return True

    if not entries:
        logger.info("No saved settings snapshots found.")
        return True

    for e in entries:
        click.echo(f"{e['cloud_name']}\t{e['name']}")
    return True


@settings.command("show", short_help="Show a saved settings snapshot.")
@click.argument("name")
@click.option("--cloud", "cloud_name", help="Cloud name namespace. Default: current cloud.")
@click.option("--out", "out_file", help="Write snapshot to a file path.")
def show_settings(name, cloud_name, out_file):
    cloud_name = resolve_cloud_name_or_current(cloud_name)
    snapshot_path = get_settings_store_snapshot_path(cloud_name, name)
    if not os.path.exists(snapshot_path):
        logger.error(f"Settings snapshot '{name}' not found for cloud '{cloud_name}'.")
        return False

    snapshot = read_json_from_file(snapshot_path)
    if out_file:
        write_json_to_file(snapshot, out_file, indent=2)
    print_json(snapshot)
    return True


@settings.command("rm", short_help="Delete a saved settings snapshot.")
@click.argument("name")
@click.option("--cloud", "cloud_name", help="Cloud name namespace. Default: current cloud.")
@click.option("-F", "--force", is_flag=True)
def rm_settings(name, cloud_name, force):
    cloud_name = resolve_cloud_name_or_current(cloud_name)
    if not force:
        if not confirm_action(f"Delete settings snapshot '{name}' for cloud '{cloud_name}'? (y/N)"):
            logger.info("Stopping.")
            return False

    deleted = delete_settings_store_snapshot(cloud_name, name)
    if not deleted:
        logger.error(f"Settings snapshot '{name}' not found for cloud '{cloud_name}'.")
        return False

    logger.info(f"Deleted settings snapshot '{name}' for cloud '{cloud_name}'.")
    return True


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

@settings.command("diff", short_help="Show drift between a snapshot and the target account.")
@click.argument("name", required=False)
@click.option("--in", "in_file", help="Diff from an explicit file path instead of the store.")
@click.option("--in-dir", "in_dir", help="Diff from a directory layout.")
@click.option("--cloud", "cloud_name", help="Cloud name namespace for saved snapshots.")
@click.option("--component", "components", multiple=True,
              help="Components to diff. Default: components present in snapshot.")
@click.option("--pick", "picks", multiple=True, nargs=3)
def diff_settings(name, in_file, in_dir, cloud_name, components, picks):
    return _run_diff(name, cloud_name, in_file, in_dir, components, picks)


def _run_diff(name, cloud_name, in_file, in_dir, components, picks):
    if not name and not in_file and not in_dir:
        print_help_and_exit()

    snapshot = _read_snapshot(in_file=in_file, in_dir=in_dir, name=name, cloud_name=cloud_name)
    if snapshot is None:
        return False

    parsed = parse_picks(picks)
    selected_components = (
        normalize_list_params(components) if components
        else (parsed.selected_components or snapshot.get("components") or list(ALL_COMPONENTS))
    )
    _validate_components(selected_components)

    drift_count = 0
    for comp in selected_components:
        if comp == "config" and "config" in snapshot and snapshot.get("config"):
            ok = diff_config_bundle(snapshot["config"], target_options=None)
            if not ok:
                drift_count += 1
            continue

        # For non-config components we run the provider's apply in dry-run + force
        # mode against the current account: that exercises the same plan logic
        # but produces output without actually modifying state. We capture the
        # plan via a pre-flight summary; the simplest correct thing is to run
        # the planner and report counts.
        bundle = snapshot.get(comp)
        if not bundle:
            continue
        provider = PROVIDERS.get(comp)
        if not provider:
            continue
        logger.info("=" * 60)
        logger.info(f"DIFF: {comp}")
        logger.info("=" * 60)
        result = provider.apply_bundle(
            bundle,
            target_options=None,
            picks=_picks_for(comp, parsed),
            related=None,
            mode="sync",       # "sync" exposes all three diff buckets
            dry_run=True,
            force=True,
        )
        if not result:
            drift_count += 1

    return drift_count == 0


def _picks_for(component, parsed):
    """Translate a Picks object into per-provider `picks` arg shape."""
    if component == "smd":
        return (parsed.smd_fields, parsed.smd_rules)
    if component == "transformations":
        return _trans_filters(parsed.transformation_names)
    if component == "upload_presets":
        return _preset_filters(parsed.upload_preset_names)
    if component == "streaming_profiles":
        return _profile_filters(parsed.streaming_profile_names)
    if component == "upload_mappings":
        return _mapping_filters(parsed.upload_mapping_folders)
    return None


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

@settings.command("restore", short_help="Restore settings to the current account.")
@click.argument("name", required=False)
@click.option("--cloud", "cloud_name", help="Cloud name namespace for saved snapshots. Default: current cloud.")
@click.option("--in", "in_file", help="Restore from an explicit file path.")
@click.option("--in-dir", "in_dir", help="Restore from a directory layout.")
@click.option("--component", "components", multiple=True,
              help="Components to restore. Default: components present in snapshot.")
@click.option("--pick", "picks", multiple=True, nargs=3)
@click.option("--smd-include-rules", is_flag=True, default=False)
@click.option("--mode", type=click.Choice(["create-missing", "upsert", "sync"], case_sensitive=False),
              default="create-missing")
@click.option("--dry-run", is_flag=True, default=False)
@click.option("-F", "--force", is_flag=True)
def restore_settings(name, cloud_name, in_file, in_dir, components, picks, smd_include_rules, mode, dry_run, force):
    parsed = parse_picks(picks)

    if not name and not in_file and not in_dir:
        try:
            is_tty = click.get_text_stream('stdin').isatty()
        except Exception:
            is_tty = False
        if not is_tty:
            print_help_and_exit()
        cloud_name = resolve_cloud_name_or_current(cloud_name)
        entries = list_settings_store_entries(cloud_name=cloud_name)
        if not entries:
            logger.info(f"No saved settings snapshots found for cloud '{cloud_name}'.")
            return False
        click.echo(f"Saved settings snapshots for '{cloud_name}':")
        for i, e in enumerate(entries, start=1):
            click.echo(f"{i}. {e['name']}")
        idx = click.prompt("Select snapshot number", type=int, default=1)
        if idx < 1 or idx > len(entries):
            raise click.UsageError(f"Invalid selection: {idx}.")
        name = entries[idx - 1]["name"]

    snapshot = _read_snapshot(in_file=in_file, in_dir=in_dir, name=name, cloud_name=cloud_name)
    if snapshot is None:
        return False

    selected_components = (
        normalize_list_params(components) if components
        else (parsed.selected_components or snapshot.get("components") or list(DEFAULT_COMPONENTS))
    )
    _validate_components(selected_components)

    return _apply_to_target(
        snapshot,
        selected_components=selected_components,
        parsed_picks=parsed,
        smd_include_rules=smd_include_rules,
        mode=mode,
        dry_run=dry_run,
        force=force,
        target_options=None,
        target_label=None,
    )


# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------

@settings.command("clone", short_help="Clone settings from current account or a snapshot to one or more targets.")
@click.argument("targets", nargs=-1)
@click.option("--from", "from_name", help="Use a saved snapshot name instead of exporting from current account.")
@click.option("--cloud", "cloud_name", help="Cloud name namespace for --from snapshots.")
@click.option("--in", "in_file", help="Use an explicit snapshot file path.")
@click.option("--in-dir", "in_dir", help="Use a snapshot directory layout.")
@click.option("--component", "components", multiple=True)
@click.option("--pick", "picks", multiple=True, nargs=3)
@click.option("--smd-include-rules", is_flag=True, default=False)
@click.option("--mode", type=click.Choice(["create-missing", "upsert", "sync"], case_sensitive=False),
              default="create-missing")
@click.option("--dry-run", is_flag=True, default=False)
@click.option("-F", "--force", is_flag=True)
def clone_settings(targets, from_name, cloud_name, in_file, in_dir, components, picks, smd_include_rules, mode, dry_run, force):
    parsed = parse_picks(picks)
    if not targets:
        raise click.UsageError("Please provide one or more target configs (CLOUDINARY_URL or saved config name).")
    if sum(bool(x) for x in (in_file, in_dir, from_name)) > 1:
        raise click.UsageError("Use only one of --in, --in-dir, or --from.")

    if in_file or in_dir or from_name:
        snapshot = _read_snapshot(
            in_file=in_file,
            in_dir=in_dir,
            name=from_name,
            cloud_name=cloud_name,
        )
        if snapshot is None:
            return False
    else:
        selected_components = (
            normalize_list_params(components) if components
            else (parsed.selected_components or list(DEFAULT_COMPONENTS))
        )
        _validate_components(selected_components)

        cloud_name_src = cloudinary.config().cloud_name
        if not cloud_name_src:
            logger.error("No Cloudinary configuration found.")
            return False

        snapshot = make_envelope(
            name="(ad-hoc)",
            cloud_name=cloud_name_src,
            components=selected_components,
            selection=_selection_record(selected_components, picks),
        )
        if "smd" in selected_components:
            snapshot["smd"] = export_smd_bundle(
                field_external_ids=_list_or_none(parsed.smd_fields),
                rule_names=_list_or_none(parsed.smd_rules),
                include_related_rules=smd_include_rules,
            )
        if "transformations" in selected_components:
            snapshot["transformations"] = export_transformations_snapshot(
                transformation_names=_trans_filters(parsed.transformation_names),
            )
        if "upload_presets" in selected_components:
            snapshot["upload_presets"] = export_upload_presets(
                preset_names=_preset_filters(parsed.upload_preset_names),
            )
        if "streaming_profiles" in selected_components:
            snapshot["streaming_profiles"] = export_streaming_profiles(
                profile_names=_profile_filters(parsed.streaming_profile_names),
            )
        if "upload_mappings" in selected_components:
            snapshot["upload_mappings"] = export_upload_mappings(
                folders=_mapping_filters(parsed.upload_mapping_folders),
            )
        if "config" in selected_components:
            snapshot["config"] = export_config_bundle()
        finalize_envelope(snapshot, ALL_COMPONENTS)

    effective_components = (
        normalize_list_params(components) if components
        else (parsed.selected_components or snapshot.get("components") or list(DEFAULT_COMPONENTS))
    )
    _validate_components(effective_components)

    ok = True
    for target in targets:
        target_config = get_cloudinary_config(target)
        if not target_config:
            ok = False
            continue
        target_options = config_to_dict(target_config)
        target_cloud = target_options.get("cloud_name", target)
        logger.info(f"Cloning settings to '{target_cloud}'...")
        res = _apply_to_target(
            snapshot,
            selected_components=effective_components,
            parsed_picks=parsed,
            smd_include_rules=smd_include_rules,
            mode=mode,
            dry_run=dry_run,
            force=force,
            target_options=target_options,
            target_label=target_cloud,
        )
        ok = ok and bool(res)

    return ok


# ---------------------------------------------------------------------------
# Apply orchestration shared between restore and clone
# ---------------------------------------------------------------------------

def _apply_to_target(
    snapshot,
    *,
    selected_components,
    parsed_picks,
    smd_include_rules,
    mode,
    dry_run,
    force,
    target_options,
    target_label,
):
    ok = True
    applied_any = False

    # Apply in design-mandated order, even if user listed components in another order.
    ordered = [c for c in APPLY_ORDER if c in selected_components]

    for comp in ordered:
        bundle = snapshot.get(comp)
        if not bundle:
            continue

        if comp == "config":
            applied_any = True
            logger.warning(
                "Config is captured for diffing only and is never applied. "
                "Use `cld settings diff --component config` to see drift; change values "
                "in the Console or via the Provisioning API."
            )
            continue

        applied_any = True
        logger.info("=" * 60)
        label = f"COMPONENT: {comp}"
        if target_label:
            label = f"{label}  -> {target_label}"
        logger.info(label)
        logger.info("=" * 60)

        if comp == "smd":
            res = apply_smd_bundle(
                bundle,
                target_options=target_options,
                dry_run=dry_run,
                force=force,
                field_external_ids=_list_or_none(parsed_picks.smd_fields),
                rule_names=_list_or_none(parsed_picks.smd_rules),
                include_related_rules=smd_include_rules,
                mode=mode,
            )
        elif comp == "transformations":
            res = apply_transformations_snapshot(
                bundle,
                target_options=target_options,
                dry_run=dry_run,
                force=force,
                transformation_names=_trans_filters(parsed_picks.transformation_names),
                mode=mode,
            )
        elif comp == "upload_presets":
            res = apply_upload_presets(
                bundle,
                target_options=target_options,
                dry_run=dry_run,
                force=force,
                preset_names=_preset_filters(parsed_picks.upload_preset_names),
                mode=mode,
            )
        elif comp == "streaming_profiles":
            res = apply_streaming_profiles(
                bundle,
                target_options=target_options,
                dry_run=dry_run,
                force=force,
                profile_names=_profile_filters(parsed_picks.streaming_profile_names),
                mode=mode,
            )
        elif comp == "upload_mappings":
            res = apply_upload_mappings(
                bundle,
                target_options=target_options,
                dry_run=dry_run,
                force=force,
                folders=_mapping_filters(parsed_picks.upload_mapping_folders),
                mode=mode,
            )
        else:
            logger.warning(f"No apply handler for component '{comp}'; skipping.")
            res = True

        ok = ok and bool(res)

    if not applied_any:
        logger.info("Nothing to apply (no supported components found in snapshot).")
        return True

    return ok
