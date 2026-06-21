"""
Upload presets provider for settings snapshots.

See settings-design.md §6.3 for the design notes.

Identity: preset `name`. The server-assigned `external_id` is treated as
noisy and stripped during normalization. `unsigned` is mutable and is part
of the create/update payload alongside the `settings` body.
"""
import logging
from multiprocessing.pool import ThreadPool
from typing import Dict, Any

import cloudinary
import cloudinary.api

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.api_utils import call_api_with_pagination
from cloudinary_cli.utils.utils import confirm_action

from ..utils.normalize import expand_names_with_patterns, index_by, sort_string_list_value
from ..utils.render import (
    c,
    diff_any,
    format_items,
    format_section,
    format_updates_with_diffs,
)


COMPONENT = "upload_presets"
PICK_KINDS = ("name",)
PICK_ALL_SENTINEL = "__ALL_UPLOAD_PRESETS__"

DEFAULT_WORKERS = 30

# Keys that should never round-trip (server-assigned / noisy).
_FORBIDDEN_TOP_LEVEL = {"external_id", "created_at", "updated_at"}

# `tags` and `allowed_formats` are commonly stored as comma-separated strings
# on Cloudinary; sorting them stabilises the comparison without changing
# the value the user wrote down (apply still sends the original).
_LIST_LIKE_KEYS = ("tags", "allowed_formats")


def _normalize_settings(settings):
    """Sort list-like fields inside `settings` for stable comparison."""
    if not isinstance(settings, dict):
        return settings
    norm = {}
    for k, v in settings.items():
        if k in _LIST_LIKE_KEYS:
            norm[k] = sort_string_list_value(v)
        elif isinstance(v, list):
            try:
                norm[k] = sorted(v, key=lambda x: (isinstance(x, dict), str(x)))
            except Exception:
                norm[k] = v
        else:
            norm[k] = v
    return norm


def _normalize_for_compare(preset):
    """Reduce a preset to a structure suitable for round-trip equality."""
    if not isinstance(preset, dict):
        return preset
    p = {k: v for k, v in preset.items() if k not in _FORBIDDEN_TOP_LEVEL}
    p["settings"] = _normalize_settings(p.get("settings") or {})
    p["unsigned"] = bool(p.get("unsigned", False))
    return p


def _needs_update(desired, target) -> bool:
    return _normalize_for_compare(desired) != _normalize_for_compare(target)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_upload_presets(preset_names=None, concurrent_workers=DEFAULT_WORKERS):
    """
    Export upload presets from the current account, including their `settings`.
    """
    logger.info("Exporting upload presets...")

    res = call_api_with_pagination(cloudinary.api.upload_presets, force=True)
    listed = res.get("presets", []) or []
    logger.info(f"Found {len(listed)} upload presets.")

    selected = _filter_list(listed, preset_names)
    if selected is not listed:
        logger.info(f"Filtered to {len(selected)} upload presets.")

    presets = []

    def _fetch(p):
        name = p.get("name")
        if not name:
            return None
        try:
            detail = cloudinary.api.upload_preset(name)
            return _serialize_preset(detail)
        except Exception as e:
            logger.warning(f"Upload presets: failed to export '{name}': {e}")
            return None

    if selected:
        with ThreadPool(min(concurrent_workers, max(1, len(selected)))) as pool:
            for entry in pool.map(_fetch, selected):
                if entry:
                    presets.append(entry)

    presets.sort(key=lambda p: p.get("name") or "")
    return {"presets": presets}


def _serialize_preset(detail):
    """Project an SDK preset detail into our snapshot form."""
    if not isinstance(detail, dict):
        return None
    return {
        "name": detail.get("name"),
        "unsigned": bool(detail.get("unsigned", False)),
        "settings": detail.get("settings") or {},
    }


def _filter_list(presets, names):
    if not names:
        return presets
    if any(n in ("*", "all", PICK_ALL_SENTINEL) for n in names):
        return presets
    universe = [p.get("name") for p in presets if p.get("name")]
    expanded = expand_names_with_patterns(universe, set(names))
    return [p for p in presets if p.get("name") in expanded]


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------

def summarize_upload_presets(bundle):
    if not bundle or not bundle.get("presets"):
        return []
    return sorted(p.get("name") for p in bundle["presets"] if p.get("name"))


# ---------------------------------------------------------------------------
# Target listing
# ---------------------------------------------------------------------------

def _list_target(target_options) -> Dict[str, Dict[str, Any]]:
    """List target presets indexed by name, with serialized bodies."""
    res = call_api_with_pagination(
        cloudinary.api.upload_presets,
        kwargs=target_options or None,
        force=True,
    )
    out = {}
    for p in res.get("presets", []) or []:
        name = p.get("name")
        if not name:
            continue
        out[name] = _serialize_preset(p) or {"name": name, "unsigned": False, "settings": {}}
    return out


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply_upload_presets(
    bundle,
    target_options=None,
    dry_run=False,
    force=False,
    preset_names=None,
    mode="create-missing",
    concurrent_workers=DEFAULT_WORKERS,
):
    mode = (mode or "create-missing").lower()
    if mode not in ("create-missing", "upsert", "sync"):
        raise ValueError(f"Unsupported upload_presets mode: {mode}")

    if not bundle or not bundle.get("presets"):
        logger.info("Upload presets: nothing to apply (empty bundle).")
        return True

    source = _filter_list(bundle["presets"], preset_names)
    source_by_name = {p["name"]: p for p in source if p.get("name")}

    try:
        target_by_name = _list_target(target_options)
    except Exception as e:
        logger.error(f"Upload presets: failed to list target presets: {e}")
        return False

    to_create = []
    to_update = []
    for name, p in source_by_name.items():
        target_p = target_by_name.get(name)
        if not target_p:
            to_create.append(p)
            continue
        if mode == "create-missing":
            continue
        if _needs_update(p, target_p):
            to_update.append(p)

    to_delete = []
    if mode == "sync":
        to_delete = sorted(set(target_by_name.keys()) - set(source_by_name.keys()))

    to_create.sort(key=lambda p: p["name"])
    to_update.sort(key=lambda p: p["name"])

    if not (to_create or to_update or to_delete):
        logger.info("Upload presets: target already matches the desired selection. Nothing to do.")
        return True

    logger.info(f"Upload presets plan (mode={mode}):")
    logger.info(f"  Create: {len(to_create)} | Update: {len(to_update)} | Delete: {len(to_delete)}")

    debug = logger.isEnabledFor(logging.DEBUG)
    update_diffs = {}
    if debug:
        for p in to_update:
            diffs = diff_any(_normalize_for_compare(p), _normalize_for_compare(target_by_name.get(p["name"])), max_diffs=40)
            if diffs:
                update_diffs[p["name"]] = diffs

    if not force:
        msg = (
            f"{c('This operation will apply upload-preset changes to the target environment:', bold=True)}\n"
            f"- presets: "
            f"{c('+' + str(len(to_create)), fg='green', bold=True)} "
            f"{c('~' + str(len(to_update)), fg='yellow', bold=True)} "
            f"{c('-' + str(len(to_delete)), fg='red', bold=True)}\n"
            f"{format_section(c('create', fg='green', bold=True), format_items([p['name'] for p in to_create]))}"
            f"{format_section(c('update', fg='yellow', bold=True), format_updates_with_diffs([p['name'] for p in to_update], update_diffs) if debug else format_items([p['name'] for p in to_update]))}"
            f"{format_section(c('delete', fg='red', bold=True), format_items(to_delete))}"
            "Continue? (y/N)"
        )
        if not confirm_action(msg):
            logger.info("Stopping.")
            return False

    if dry_run:
        logger.info(
            f"Upload presets dry-run: +{len(to_create)} ~{len(to_update)} -{len(to_delete)}."
        )
        return True

    return _apply_changes(to_create, to_update, to_delete, target_options, mode, concurrent_workers)


def _apply_changes(to_create, to_update, to_delete, target_options, mode, concurrent_workers) -> bool:
    def _create(p):
        try:
            cloudinary.api.create_upload_preset(
                name=p["name"],
                unsigned=bool(p.get("unsigned", False)),
                **(p.get("settings") or {}),
                **(target_options or {}),
            )
            logger.info(f"Upload presets: created '{p['name']}'.")
            return True
        except Exception as e:
            if mode == "create-missing" and _is_already_exists(e):
                logger.debug(f"Upload presets: '{p['name']}' already exists (skipped).")
                return True
            logger.error(f"Upload presets: failed to create '{p['name']}': {e}")
            return False

    def _update(p):
        try:
            cloudinary.api.update_upload_preset(
                p["name"],
                unsigned=bool(p.get("unsigned", False)),
                **(p.get("settings") or {}),
                **(target_options or {}),
            )
            logger.info(f"Upload presets: updated '{p['name']}'.")
            return True
        except Exception as e:
            logger.error(f"Upload presets: failed to update '{p['name']}': {e}")
            return False

    def _delete(name):
        try:
            cloudinary.api.delete_upload_preset(name, **(target_options or {}))
            logger.info(f"Upload presets: deleted '{name}'.")
            return True
        except Exception as e:
            logger.error(f"Upload presets: failed to delete '{name}': {e}")
            return False

    workers = max(1, min(concurrent_workers, max(len(to_create), len(to_update), len(to_delete), 1)))
    with ThreadPool(workers) as pool:
        results = []
        if to_create:
            results.extend(pool.map(_create, to_create))
        if to_update:
            results.extend(pool.map(_update, to_update))
        if to_delete:
            results.extend(pool.map(_delete, to_delete))

    return all(results) if results else True


def _is_already_exists(exc) -> bool:
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if status == 409:
        return True
    msg = (str(exc) or "").lower()
    return "already exists" in msg


# ---------------------------------------------------------------------------
# Standalone delete
# ---------------------------------------------------------------------------

def delete_upload_presets(
    target_options=None,
    dry_run=False,
    force=False,
    preset_names=None,
    concurrent_workers=DEFAULT_WORKERS,
):
    requested = list(preset_names or [])
    if not requested:
        logger.info("Upload presets: nothing selected for deletion.")
        return True

    try:
        target_by_name = _list_target(target_options)
    except Exception as e:
        logger.error(f"Upload presets: failed to list: {e}")
        return False

    universe = list(target_by_name.keys())
    expanded = set()
    if any(n in ("*", "all", PICK_ALL_SENTINEL) for n in requested):
        expanded |= set(universe)
    else:
        expanded |= expand_names_with_patterns(universe, set(requested))

    to_delete = sorted(expanded)
    missing = [n for n in requested if n not in universe and n not in ("*", "all", PICK_ALL_SENTINEL) and not any(ch in n for ch in "*?[")]
    if missing:
        logger.warning(f"Upload presets: not found (skipping): {', '.join(missing)}")

    if not to_delete:
        logger.info("Upload presets: nothing to delete.")
        return True

    sep = "-" * 60
    logger.info(sep)
    logger.info(c(f"Upload presets to delete ({len(to_delete)}):", fg="cyan"))
    for name in to_delete:
        logger.info(c(f"  - {name}", fg="yellow"))
    logger.info(sep)

    if dry_run:
        logger.info(f"Upload presets dry-run delete: -{len(to_delete)}.")
        return True

    if not force:
        if not confirm_action(f"Delete {len(to_delete)} upload preset(s)? (y/N)"):
            logger.info("Stopping.")
            return False

    def _delete(name):
        try:
            cloudinary.api.delete_upload_preset(name, **(target_options or {}))
            logger.info(f"Upload presets: deleted '{name}'.")
            return True, name, None
        except Exception as e:
            logger.error(f"Upload presets: failed to delete '{name}': {e}")
            return False, name, str(e)

    workers = max(1, min(concurrent_workers, len(to_delete)))
    with ThreadPool(workers) as pool:
        results = pool.map(_delete, to_delete)

    failures = [(n, err) for ok, n, err in results if not ok]
    return not failures


# ---------------------------------------------------------------------------
# Uniform contract
# ---------------------------------------------------------------------------

def export_bundle(*, picks=None, related=None):
    return export_upload_presets(preset_names=picks)


def summarize_bundle(bundle):
    return summarize_upload_presets(bundle)


def apply_bundle(
    bundle,
    *,
    target_options=None,
    picks=None,
    related=None,
    mode="create-missing",
    dry_run=False,
    force=False,
):
    return apply_upload_presets(
        bundle,
        target_options=target_options,
        dry_run=dry_run,
        force=force,
        preset_names=picks,
        mode=mode,
    )


def delete_items(
    *,
    target_options=None,
    picks=None,
    related=None,
    dry_run=False,
    force=False,
):
    return delete_upload_presets(
        target_options=target_options,
        dry_run=dry_run,
        force=force,
        preset_names=picks,
    )
