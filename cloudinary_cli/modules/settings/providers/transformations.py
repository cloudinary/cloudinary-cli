"""
Transformations provider for settings snapshots.

Exports, applies, and deletes named transformations using the same uniform
contract documented in settings-design.md §3.1.

Identity: transformation `name`. Cloudinary returns named transformations
prefixed with `t_`; create/update/delete calls expect the unprefixed form.
"""
import logging
from multiprocessing.pool import ThreadPool
from typing import Dict, List, Any

import click
import cloudinary
import cloudinary.api

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.api_utils import call_api_with_pagination
from cloudinary_cli.utils.utils import confirm_action

from ..utils.normalize import expand_names_with_patterns, index_by
from ..utils.render import (
    c,
    diff_any,
    format_items,
    format_section,
    format_updates_with_diffs,
)


COMPONENT = "transformations"
PICK_KINDS = ("name",)
PICK_ALL_SENTINEL = "__ALL_TRANSFORMATIONS__"

DEFAULT_WORKERS = 30


# ---------------------------------------------------------------------------
# Identity / name handling
# ---------------------------------------------------------------------------

def _strip_named_prefix(name: str) -> str:
    """
    Cloudinary Admin API returns named transformations with leading 't_'.
    Creation/update/delete calls expect the raw name without the 't_' prefix.
    """
    if isinstance(name, str) and name.startswith("t_"):
        return name[2:]
    return name


def _ensure_named_prefix(name: str) -> str:
    """Inverse of `_strip_named_prefix` for stable identity comparison."""
    if isinstance(name, str) and not name.startswith("t_"):
        return f"t_{name}"
    return name


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _normalize_chain(chain: Any):
    """
    Normalize a transformation chain for equality comparison.

    Step order is preserved; within each step (a dict) we sort items so that
    `{w:100, h:50}` and `{h:50, w:100}` compare equal.
    """
    if not isinstance(chain, list):
        return chain
    normalized = []
    for step in chain:
        if isinstance(step, dict):
            normalized.append(tuple(sorted(step.items())))
        else:
            normalized.append(step)
    return tuple(normalized)


def _normalize_for_compare(t: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reduce a transformation dict to the minimum we want to round-trip.

    We deliberately drop:
        - `used`        : usage flag, server-side, not part of identity.
        - `info`        : alias of `transformation`; we already store `transformation`.
        - `created_at` / `updated_at` : noise.
        - any name-prefix mismatch handled by stripping `t_`.
    """
    if not isinstance(t, dict):
        return t
    return {
        "name": _ensure_named_prefix(t.get("name") or ""),
        "transformation": _normalize_chain(t.get("transformation")),
        "allowed_for_strict": bool(t.get("allowed_for_strict", False)),
    }


def _needs_update(desired: Dict[str, Any], target: Dict[str, Any]) -> bool:
    return _normalize_for_compare(desired) != _normalize_for_compare(target)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_transformations_snapshot(transformation_names=None, concurrent_workers=DEFAULT_WORKERS):
    """
    Export named transformations from the current account.

    Args:
        transformation_names: Optional list of names (or wildcard patterns).
                              If None or contains the PICK_ALL_SENTINEL, exports all.
    """
    logger.info("Exporting transformations...")

    result = call_api_with_pagination(
        cloudinary.api.transformations,
        kwargs={"named": True},
        force=True,
    )
    all_transformations = result.get("transformations", [])
    logger.info(f"Found {len(all_transformations)} named transformations.")

    selected = _filter_transformation_list(all_transformations, transformation_names)
    if selected is not all_transformations:
        logger.info(f"Filtered to {len(selected)} transformations.")

    transformations = []

    def _fetch_one(t):
        name = t.get("name")
        if not name:
            return None
        try:
            detail = cloudinary.api.transformation(name)
            return {
                "name": name,
                "transformation": detail.get("info", []),
                "allowed_for_strict": detail.get("allowed_for_strict", False),
            }
        except Exception as e:
            logger.warning(f"Failed to export transformation '{name}': {e}")
            return None

    if selected:
        with ThreadPool(min(concurrent_workers, max(1, len(selected)))) as pool:
            for entry in pool.map(_fetch_one, selected):
                if entry:
                    transformations.append(entry)

    transformations.sort(key=lambda t: t.get("name") or "")
    return {"transformations": transformations}


def _filter_transformation_list(all_transformations, transformation_names):
    """
    Filter a list of transformation dicts by names/patterns.

    None or PICK_ALL_SENTINEL means "all"; otherwise we expand wildcards.
    """
    if not transformation_names:
        return all_transformations

    if any(p in ("*", "all", PICK_ALL_SENTINEL, "__ALL__") for p in transformation_names):
        return all_transformations

    universe = [t.get("name") for t in all_transformations if t.get("name")]
    expanded = expand_names_with_patterns(universe, set(transformation_names))
    return [t for t in all_transformations if t.get("name") in expanded]


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------

def summarize_transformations_snapshot(bundle):
    """Return transformation names in a deterministic order."""
    if not bundle or not bundle.get("transformations"):
        return []
    return sorted(t.get("name") for t in bundle["transformations"] if t.get("name"))


# ---------------------------------------------------------------------------
# Target listing
# ---------------------------------------------------------------------------

def _list_target_transformation_names(target_options):
    result = call_api_with_pagination(
        cloudinary.api.transformations,
        kwargs={**(target_options or {}), "named": True},
        force=True,
    )
    return [t.get("name") for t in result.get("transformations", []) if t.get("name")]


def _fetch_target_details(names: List[str], target_options: Dict[str, Any], concurrent_workers: int) -> Dict[str, Any]:
    """Parallel-fetch full details for target transformations."""
    if not names:
        return {}

    failures = []

    def _fetch(name):
        try:
            detail = cloudinary.api.transformation(name, **(target_options or {}))
            return {
                "name": name,
                "transformation": detail.get("info", []),
                "allowed_for_strict": detail.get("allowed_for_strict", False),
            }
        except Exception as e:
            failures.append((name, str(e)))
            return {
                "name": name,
                "transformation": None,
                "allowed_for_strict": None,
                "_fetch_failed": True,
            }

    with ThreadPool(min(concurrent_workers, max(1, len(names)))) as pool:
        results = pool.map(_fetch, names)

    if failures:
        failed_names = ", ".join(n for n, _ in failures)
        logger.warning(
            f"Transformations: failed to fetch details for {len(failures)} item(s): {failed_names}"
        )

    return {r["name"]: r for r in results}


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def _build_plan(source_list, target_names, target_details, mode):
    """
    Build (to_create, to_update, to_delete) lists from source/target state.

    create-missing skips updates and deletes. upsert skips deletes. sync does all.
    """
    source_by_name = {t["name"]: t for t in source_list if t.get("name")}
    target_set = set(target_names)

    to_create = []
    to_update = []

    for name, t in source_by_name.items():
        if name not in target_set:
            to_create.append(t)
            continue
        if mode == "create-missing":
            continue
        target_t = target_details.get(name) if target_details else None
        if not target_t or target_t.get("_fetch_failed"):
            logger.debug(f"Transformations: skipping diff for '{name}' (target detail unavailable).")
            continue
        if _needs_update(t, target_t):
            to_update.append(t)

    to_delete = []
    if mode == "sync":
        to_delete = sorted(target_set - set(source_by_name.keys()))

    to_create.sort(key=lambda t: t.get("name") or "")
    to_update.sort(key=lambda t: t.get("name") or "")
    return to_create, to_update, to_delete


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply_transformations_snapshot(
    bundle,
    target_options=None,
    dry_run=False,
    force=False,
    transformation_names=None,
    mode="create-missing",
    concurrent_workers=DEFAULT_WORKERS,
):
    """
    Apply transformations from a bundle to the target environment.

    Modes:
        - create-missing: create only missing transformations
        - upsert: create missing + update differing
        - sync: upsert + delete extras (transformations in target not in source)
    """
    mode = (mode or "create-missing").lower()
    if mode not in ("create-missing", "upsert", "sync"):
        raise ValueError(f"Unsupported transformations mode: {mode}")

    if not bundle or not bundle.get("transformations"):
        logger.info("Transformations: nothing to apply (empty bundle).")
        return True

    source_list = bundle["transformations"]
    if transformation_names:
        source_list = _filter_transformation_list(source_list, transformation_names)

    try:
        target_names = _list_target_transformation_names(target_options)
    except Exception as e:
        logger.error(f"Transformations: failed to list target transformations: {e}")
        return False

    if mode == "create-missing":
        target_details = {}
    else:
        target_details = _fetch_target_details(target_names, target_options, concurrent_workers)

    to_create, to_update, to_delete = _build_plan(source_list, target_names, target_details, mode)

    if not (to_create or to_update or to_delete):
        logger.info("Transformations: target already matches the desired selection. Nothing to do.")
        return True

    _print_plan(to_create, to_update, to_delete, mode, target_details)

    if not force:
        if not _confirm_plan(to_create, to_update, to_delete, target_details):
            logger.info("Stopping.")
            return False

    if dry_run:
        logger.info(
            f"Transformations dry-run: +{len(to_create)} ~{len(to_update)} -{len(to_delete)}."
        )
        return True

    return _apply_changes(to_create, to_update, to_delete, target_options, mode, concurrent_workers)


def _print_plan(to_create, to_update, to_delete, mode, target_details):
    """Log a tabular plan summary at INFO level."""
    logger.info(f"Transformations plan (mode={mode}):")
    logger.info(
        f"  Create: {len(to_create)} | Update: {len(to_update)} | Delete: {len(to_delete)}"
    )

    if logger.isEnabledFor(logging.DEBUG):
        for t in to_update:
            target_t = target_details.get(t["name"])
            if target_t and not target_t.get("_fetch_failed"):
                diffs = diff_any(_normalize_for_compare(t), _normalize_for_compare(target_t))
                if diffs:
                    logger.debug(f"Transformations: diff for '{t['name']}':")
                    for d in diffs[:40]:
                        logger.debug(f"  {d}")


def _confirm_plan(to_create, to_update, to_delete, target_details) -> bool:
    """Build a colorized confirm message and ask the user."""
    debug = logger.isEnabledFor(logging.DEBUG)
    update_diffs_by_name = {}
    if debug:
        for t in to_update:
            target_t = target_details.get(t["name"])
            if target_t and not target_t.get("_fetch_failed"):
                diffs = diff_any(_normalize_for_compare(t), _normalize_for_compare(target_t), max_diffs=40)
                if diffs:
                    update_diffs_by_name[t["name"]] = diffs

    create_block = format_items([t["name"] for t in to_create])
    update_block = (
        format_updates_with_diffs([t["name"] for t in to_update], update_diffs_by_name)
        if debug else format_items([t["name"] for t in to_update])
    )
    delete_block = format_items(to_delete)

    msg = (
        f"{c('This operation will apply named-transformation changes to the target environment:', bold=True)}\n"
        f"- transformations: "
        f"{c('+' + str(len(to_create)), fg='green', bold=True)} "
        f"{c('~' + str(len(to_update)), fg='yellow', bold=True)} "
        f"{c('-' + str(len(to_delete)), fg='red', bold=True)}\n"
        f"{format_section(c('create', fg='green', bold=True), create_block)}"
        f"{format_section(c('update', fg='yellow', bold=True), update_block)}"
        f"{format_section(c('delete', fg='red', bold=True), delete_block)}"
        "Continue? (y/N)"
    )
    return confirm_action(msg)


def _apply_changes(to_create, to_update, to_delete, target_options, mode, concurrent_workers) -> bool:
    """Apply a plan in parallel; return True iff every leg succeeded."""
    def _create(t):
        try:
            cloudinary.api.create_transformation(
                _strip_named_prefix(t["name"]),
                definition={"transformation": t["transformation"]},
                allowed_for_strict=t.get("allowed_for_strict", False),
                **(target_options or {}),
            )
            logger.info(f"Transformations: created '{t['name']}'.")
            return True
        except Exception as e:
            if mode == "create-missing" and _is_already_exists(e):
                logger.debug(f"Transformations: '{t['name']}' already exists (skipped).")
                return True
            logger.error(f"Transformations: failed to create '{t['name']}': {e}")
            return False

    def _update(t):
        try:
            cloudinary.api.update_transformation(
                _strip_named_prefix(t["name"]),
                definition={"transformation": t["transformation"]},
                allowed_for_strict=t.get("allowed_for_strict", False),
                unsafe_update=True,
                **(target_options or {}),
            )
            logger.info(f"Transformations: updated '{t['name']}'.")
            return True
        except Exception as e:
            logger.error(f"Transformations: failed to update '{t['name']}': {e}")
            return False

    def _delete(name):
        try:
            cloudinary.api.delete_transformation(_strip_named_prefix(name), **(target_options or {}))
            logger.info(f"Transformations: deleted '{name}'.")
            return True
        except Exception as e:
            logger.error(f"Transformations: failed to delete '{name}': {e}")
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
    """
    Conservative match for the SDK's "already exists" failure.

    We check the SDK's HTTP status (preferred) and fall back to a substring
    check on the message — but only for the conflict marker, never the generic
    "409" substring (which can appear in unrelated error text).
    """
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if status == 409:
        return True
    msg = str(exc) or ""
    return "already exists" in msg.lower()


# ---------------------------------------------------------------------------
# Standalone delete
# ---------------------------------------------------------------------------

def delete_transformations(
    target_options=None,
    dry_run=False,
    force=False,
    transformation_names=None,
    concurrent_workers=DEFAULT_WORKERS,
):
    """Delete selected named transformations from the target environment."""
    try:
        result = call_api_with_pagination(
            cloudinary.api.transformations,
            kwargs={**(target_options or {}), "named": True},
            force=True,
        )
        all_transformations = result.get("transformations", [])
    except Exception as e:
        logger.error(f"Transformations: failed to list: {e}")
        return False

    universe = [t.get("name") for t in all_transformations if t.get("name")]

    requested = list(transformation_names or [])
    if not requested:
        logger.info("Transformations: nothing selected for deletion.")
        return True

    expanded = expand_names_with_patterns(universe, set(
        n for n in requested if n not in ("*", "all", PICK_ALL_SENTINEL, "__ALL__")
    ))
    if any(n in ("*", "all", PICK_ALL_SENTINEL, "__ALL__") for n in requested):
        expanded |= set(universe)

    to_delete = sorted(expanded)
    missing = sorted(set(requested) - set(universe) - {p for p in requested if any(ch in p for ch in "*?[")} - {"*", "all", PICK_ALL_SENTINEL, "__ALL__"})
    if missing:
        logger.warning(
            f"Transformations: not found (skipping): {', '.join(missing)}"
        )

    if not to_delete:
        logger.info("Transformations: nothing to delete.")
        return True

    sep = "-" * 60
    logger.info(sep)
    logger.info(c(f"Transformations to delete ({len(to_delete)}):", fg="cyan"))
    for name in to_delete:
        logger.info(c(f"  - {name}", fg="yellow"))
    logger.info(sep)

    if dry_run:
        logger.info(f"Transformations dry-run delete: -{len(to_delete)}.")
        return True

    if not force:
        if not confirm_action(f"Delete {len(to_delete)} transformation(s)? (y/N)"):
            logger.info("Stopping.")
            return False

    def _delete(name):
        try:
            cloudinary.api.delete_transformation(_strip_named_prefix(name), **(target_options or {}))
            logger.info(f"Transformations: deleted '{name}'.")
            return True, name, None
        except Exception as e:
            logger.error(f"Transformations: failed to delete '{name}': {e}")
            return False, name, str(e)

    workers = max(1, min(concurrent_workers, len(to_delete)))
    with ThreadPool(workers) as pool:
        results = pool.map(_delete, to_delete)

    successes = sum(1 for ok, _, _ in results if ok)
    failures = [(n, err) for ok, n, err in results if not ok]

    logger.info(sep)
    summary = c(
        f"Transformations delete summary: total={len(results)}, deleted={successes}, failed={len(failures)}",
        fg="green" if not failures else "yellow",
    )
    logger.info(summary)
    if failures:
        logger.error(c("Transformations delete failures:", fg="red"))
        for name, err in failures:
            logger.error(c(f"  - {name}: {err}", fg="red"))
    logger.info(sep)

    return not failures


# ---------------------------------------------------------------------------
# Uniform contract aliases (settings-design.md §3.1)
# ---------------------------------------------------------------------------

def export_bundle(*, picks=None, related=None):
    return export_transformations_snapshot(transformation_names=picks)


def summarize_bundle(bundle):
    return summarize_transformations_snapshot(bundle)


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
    return apply_transformations_snapshot(
        bundle,
        target_options=target_options,
        dry_run=dry_run,
        force=force,
        transformation_names=picks,
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
    return delete_transformations(
        target_options=target_options,
        dry_run=dry_run,
        force=force,
        transformation_names=picks,
    )
