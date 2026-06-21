"""
Upload mappings provider for settings snapshots.

See settings-design.md §6.5 for the design notes.

Identity: `folder`. Mappings have only one mutable field, `template`, so the
diff/plan logic is straightforward.
"""
from multiprocessing.pool import ThreadPool
from typing import Dict, Any

import cloudinary
import cloudinary.api

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.api_utils import call_api_with_pagination
from cloudinary_cli.utils.utils import confirm_action

from ..utils.normalize import expand_names_with_patterns
from ..utils.render import (
    c,
    format_items,
    format_section,
)


COMPONENT = "upload_mappings"
PICK_KINDS = ("folder",)
PICK_ALL_SENTINEL = "__ALL_UPLOAD_MAPPINGS__"

DEFAULT_WORKERS = 30

_FORBIDDEN_KEYS = {"external_id", "created_at", "updated_at"}


def _normalize_mapping(m):
    if not isinstance(m, dict):
        return m
    return {
        "folder": m.get("folder"),
        "template": m.get("template"),
    }


def _needs_update(desired, target) -> bool:
    return _normalize_mapping(desired) != _normalize_mapping(target)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_upload_mappings(folders=None):
    logger.info("Exporting upload mappings...")
    res = call_api_with_pagination(cloudinary.api.upload_mappings, force=True)
    listed = res.get("mappings", []) or []
    logger.info(f"Found {len(listed)} upload mappings.")

    selected = _filter_list(listed, folders)
    if selected is not listed:
        logger.info(f"Filtered to {len(selected)} upload mappings.")

    mappings = [_normalize_mapping(m) for m in selected if m.get("folder")]
    mappings.sort(key=lambda m: m.get("folder") or "")
    return {"mappings": mappings}


def _filter_list(mappings, folders):
    if not folders:
        return mappings
    if any(f in ("*", "all", PICK_ALL_SENTINEL) for f in folders):
        return mappings
    universe = [m.get("folder") for m in mappings if m.get("folder")]
    expanded = expand_names_with_patterns(universe, set(folders))
    return [m for m in mappings if m.get("folder") in expanded]


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------

def summarize_upload_mappings(bundle):
    if not bundle or not bundle.get("mappings"):
        return []
    return sorted(m.get("folder") for m in bundle["mappings"] if m.get("folder"))


# ---------------------------------------------------------------------------
# Target listing
# ---------------------------------------------------------------------------

def _list_target(target_options) -> Dict[str, Dict[str, Any]]:
    res = call_api_with_pagination(
        cloudinary.api.upload_mappings,
        kwargs=target_options or None,
        force=True,
    )
    return {m.get("folder"): _normalize_mapping(m) for m in (res.get("mappings", []) or []) if m.get("folder")}


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply_upload_mappings(
    bundle,
    target_options=None,
    dry_run=False,
    force=False,
    folders=None,
    mode="create-missing",
    concurrent_workers=DEFAULT_WORKERS,
):
    mode = (mode or "create-missing").lower()
    if mode not in ("create-missing", "upsert", "sync"):
        raise ValueError(f"Unsupported upload_mappings mode: {mode}")

    if not bundle or not bundle.get("mappings"):
        logger.info("Upload mappings: nothing to apply (empty bundle).")
        return True

    source = _filter_list(bundle["mappings"], folders)
    source_by_folder = {m["folder"]: m for m in source if m.get("folder")}

    try:
        target_by_folder = _list_target(target_options)
    except Exception as e:
        logger.error(f"Upload mappings: failed to list target: {e}")
        return False

    to_create = []
    to_update = []
    for folder, m in source_by_folder.items():
        target_m = target_by_folder.get(folder)
        if not target_m:
            to_create.append(m)
            continue
        if mode == "create-missing":
            continue
        if _needs_update(m, target_m):
            to_update.append(m)

    to_delete = []
    if mode == "sync":
        to_delete = sorted(set(target_by_folder.keys()) - set(source_by_folder.keys()))

    to_create.sort(key=lambda m: m["folder"])
    to_update.sort(key=lambda m: m["folder"])

    if not (to_create or to_update or to_delete):
        logger.info("Upload mappings: target already matches the desired selection. Nothing to do.")
        return True

    logger.info(f"Upload mappings plan (mode={mode}):")
    logger.info(f"  Create: {len(to_create)} | Update: {len(to_update)} | Delete: {len(to_delete)}")

    def _disp(m):
        return f"{m['folder']} -> {m.get('template', '')}"

    if not force:
        msg = (
            f"{c('This operation will apply upload-mapping changes to the target environment:', bold=True)}\n"
            f"- mappings: "
            f"{c('+' + str(len(to_create)), fg='green', bold=True)} "
            f"{c('~' + str(len(to_update)), fg='yellow', bold=True)} "
            f"{c('-' + str(len(to_delete)), fg='red', bold=True)}\n"
            f"{format_section(c('create', fg='green', bold=True), format_items([_disp(m) for m in to_create]))}"
            f"{format_section(c('update', fg='yellow', bold=True), format_items([_disp(m) for m in to_update]))}"
            f"{format_section(c('delete', fg='red', bold=True), format_items(to_delete))}"
            "Continue? (y/N)"
        )
        if not confirm_action(msg):
            logger.info("Stopping.")
            return False

    if dry_run:
        logger.info(f"Upload mappings dry-run: +{len(to_create)} ~{len(to_update)} -{len(to_delete)}.")
        return True

    return _apply_changes(to_create, to_update, to_delete, target_options, mode, concurrent_workers)


def _apply_changes(to_create, to_update, to_delete, target_options, mode, concurrent_workers) -> bool:
    def _create(m):
        try:
            cloudinary.api.create_upload_mapping(
                m["folder"],
                template=m.get("template"),
                **(target_options or {}),
            )
            logger.info(f"Upload mappings: created '{m['folder']}'.")
            return True
        except Exception as e:
            if mode == "create-missing" and _is_already_exists(e):
                logger.debug(f"Upload mappings: '{m['folder']}' already exists (skipped).")
                return True
            logger.error(f"Upload mappings: failed to create '{m['folder']}': {e}")
            return False

    def _update(m):
        try:
            cloudinary.api.update_upload_mapping(
                m["folder"],
                template=m.get("template"),
                **(target_options or {}),
            )
            logger.info(f"Upload mappings: updated '{m['folder']}'.")
            return True
        except Exception as e:
            logger.error(f"Upload mappings: failed to update '{m['folder']}': {e}")
            return False

    def _delete(folder):
        try:
            cloudinary.api.delete_upload_mapping(folder, **(target_options or {}))
            logger.info(f"Upload mappings: deleted '{folder}'.")
            return True
        except Exception as e:
            logger.error(f"Upload mappings: failed to delete '{folder}': {e}")
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
    return "already exists" in (str(exc) or "").lower()


# ---------------------------------------------------------------------------
# Standalone delete
# ---------------------------------------------------------------------------

def delete_upload_mappings(
    target_options=None,
    dry_run=False,
    force=False,
    folders=None,
    concurrent_workers=DEFAULT_WORKERS,
):
    requested = list(folders or [])
    if not requested:
        logger.info("Upload mappings: nothing selected for deletion.")
        return True

    try:
        target_by_folder = _list_target(target_options)
    except Exception as e:
        logger.error(f"Upload mappings: failed to list: {e}")
        return False

    universe = list(target_by_folder.keys())
    expanded = set()
    if any(n in ("*", "all", PICK_ALL_SENTINEL) for n in requested):
        expanded |= set(universe)
    else:
        expanded |= expand_names_with_patterns(universe, set(requested))

    to_delete = sorted(expanded)
    missing = [n for n in requested if n not in universe and n not in ("*", "all", PICK_ALL_SENTINEL) and not any(ch in n for ch in "*?[")]
    if missing:
        logger.warning(f"Upload mappings: not found (skipping): {', '.join(missing)}")

    if not to_delete:
        logger.info("Upload mappings: nothing to delete.")
        return True

    sep = "-" * 60
    logger.info(sep)
    logger.info(c(f"Upload mappings to delete ({len(to_delete)}):", fg="cyan"))
    for n in to_delete:
        logger.info(c(f"  - {n}", fg="yellow"))
    logger.info(sep)

    if dry_run:
        logger.info(f"Upload mappings dry-run delete: -{len(to_delete)}.")
        return True

    if not force:
        if not confirm_action(f"Delete {len(to_delete)} upload mapping(s)? (y/N)"):
            logger.info("Stopping.")
            return False

    def _delete(folder):
        try:
            cloudinary.api.delete_upload_mapping(folder, **(target_options or {}))
            logger.info(f"Upload mappings: deleted '{folder}'.")
            return True, folder, None
        except Exception as e:
            logger.error(f"Upload mappings: failed to delete '{folder}': {e}")
            return False, folder, str(e)

    workers = max(1, min(concurrent_workers, len(to_delete)))
    with ThreadPool(workers) as pool:
        results = pool.map(_delete, to_delete)

    failures = [(f, err) for ok, f, err in results if not ok]
    return not failures


# ---------------------------------------------------------------------------
# Uniform contract
# ---------------------------------------------------------------------------

def export_bundle(*, picks=None, related=None):
    return export_upload_mappings(folders=picks)


def summarize_bundle(bundle):
    return summarize_upload_mappings(bundle)


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
    return apply_upload_mappings(
        bundle,
        target_options=target_options,
        dry_run=dry_run,
        force=force,
        folders=picks,
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
    return delete_upload_mappings(
        target_options=target_options,
        dry_run=dry_run,
        force=force,
        folders=picks,
    )
