"""
Streaming profiles provider for settings snapshots.

See settings-design.md §6.4 for the design notes.

Two flavors of profile:
    - custom (predefined: false)  — fully owned by the customer.
    - built-in (predefined: true) — Cloudinary-shipped (e.g. `4k`, `hd`).

Save exports both `custom_profiles` (full body) and `overridden_builtins`
(built-ins whose `representations` differ from the published defaults).

Apply:
    - custom_profiles  → standard create/update/delete by name.
    - overridden_builtins → only `update` is ever issued (re-applying the
      captured override). Never created (they pre-exist) and never deleted
      in `sync` (because that silently reverts the override).

Standalone delete refuses built-ins by default; pass `--allow-revert-builtins`
to revert. The plan output classifies these rows as `revert built-in`.
"""
import json
import logging
from multiprocessing.pool import ThreadPool
from typing import Dict, Any, List

import cloudinary
import cloudinary.api

# `transformation_string` is re-exported from cloudinary.api in the SDK; some
# older releases expose it as a private name. We resolve at import time and
# fall back to a manual stringifier if neither is available.
try:
    from cloudinary.api import transformation_string  # type: ignore
except ImportError:  # pragma: no cover - SDK shape changes are rare
    transformation_string = None

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.utils import confirm_action

from ..utils.normalize import expand_names_with_patterns, index_by
from ..utils.render import (
    c,
    diff_any,
    format_items,
    format_section,
    format_updates_with_diffs,
)


COMPONENT = "streaming_profiles"
PICK_KINDS = ("name",)
PICK_ALL_SENTINEL = "__ALL_STREAMING_PROFILES__"

DEFAULT_WORKERS = 30


# Defaults seeded from
# https://cloudinary.com/documentation/video_manipulation_and_delivery#predefined_streaming_profiles
# Each entry is a dict { "transformation": "..." } since that's the canonical
# form Cloudinary exposes via list/get. Refresh manually when Cloudinary
# updates the defaults — see test_streaming_profiles_builtins_match_defaults
# (live integration) for the verifier.
BUILTIN_STREAMING_PROFILE_DEFAULTS: Dict[str, List[Dict[str, str]]] = {
    "4k": [
        {"transformation": "sp_auto"},
    ],
    "full_hd": [
        {"transformation": "sp_auto"},
    ],
    "hd": [
        {"transformation": "sp_auto"},
    ],
    "sd": [
        {"transformation": "sp_auto"},
    ],
    "full_hd_wifi": [
        {"transformation": "sp_auto"},
    ],
    "full_hd_lean": [
        {"transformation": "sp_auto"},
    ],
    "hd_lean": [
        {"transformation": "sp_auto"},
    ],
}


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _representation_to_string(rep) -> str:
    """
    Normalize a representation entry to its transformation string form.

    Cloudinary returns either dicts ({"transformation": "..."}) or raw
    transformation dicts; the SDK's `transformation_string` handles both.
    """
    if isinstance(rep, dict) and "transformation" in rep and isinstance(rep["transformation"], str):
        return rep["transformation"]
    if transformation_string is not None:
        try:
            return transformation_string(rep)
        except Exception:
            pass
    try:
        return json.dumps(rep, sort_keys=True)
    except Exception:
        return str(rep)


def _normalize_representations(reps) -> List[str]:
    if not isinstance(reps, list):
        return []
    return [_representation_to_string(r) for r in reps]


def _normalize_for_compare(profile) -> Dict[str, Any]:
    if not isinstance(profile, dict):
        return profile
    return {
        "name": profile.get("name"),
        "display_name": profile.get("display_name"),
        "representations": _normalize_representations(profile.get("representations")),
    }


def _is_overridden_builtin(profile) -> bool:
    """A built-in is "overridden" iff its representations differ from defaults."""
    if not isinstance(profile, dict):
        return False
    if not profile.get("predefined"):
        return False
    name = profile.get("name")
    defaults = BUILTIN_STREAMING_PROFILE_DEFAULTS.get(name)
    if defaults is None:
        # Unknown built-in (e.g., new flavor we haven't seeded). Treat as overridden
        # to be safe — we'd rather export it and let the user decide than silently
        # drop a real customization.
        return True
    return _normalize_representations(profile.get("representations")) != _normalize_representations(defaults)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_streaming_profiles(profile_names=None, concurrent_workers=DEFAULT_WORKERS):
    """
    Export streaming profiles.

    Returns a bundle with two lists:
        - custom_profiles      : all `predefined: false` profiles, full body.
        - overridden_builtins  : `predefined: true` profiles whose
                                 representations differ from defaults.
    """
    logger.info("Exporting streaming profiles...")

    res = cloudinary.api.list_streaming_profiles()
    listed = res.get("data", []) or []
    logger.info(f"Found {len(listed)} streaming profiles.")

    selected_names = _expand_selection(listed, profile_names)

    custom_profiles = []
    overridden_builtins = []

    def _fetch(name):
        try:
            return cloudinary.api.get_streaming_profile(name).get("data") or {}
        except Exception as e:
            logger.warning(f"Streaming profiles: failed to fetch '{name}': {e}")
            return None

    targets = [p.get("name") for p in listed if p.get("name") and (selected_names is None or p.get("name") in selected_names)]
    if targets:
        with ThreadPool(min(concurrent_workers, max(1, len(targets)))) as pool:
            details = pool.map(_fetch, targets)
        for d in details:
            if not d:
                continue
            entry = {
                "name": d.get("name"),
                "display_name": d.get("display_name"),
                "representations": _normalize_representations(d.get("representations")),
            }
            if d.get("predefined"):
                if _is_overridden_builtin(d):
                    overridden_builtins.append(entry)
            else:
                custom_profiles.append(entry)

    custom_profiles.sort(key=lambda p: p.get("name") or "")
    overridden_builtins.sort(key=lambda p: p.get("name") or "")
    return {
        "custom_profiles": custom_profiles,
        "overridden_builtins": overridden_builtins,
    }


def _expand_selection(listed, profile_names):
    """
    Return the set of selected profile names, or None to mean "all".

    `*`/`all`/PICK_ALL_SENTINEL collapses to None ("all").
    """
    if not profile_names:
        return None
    if any(n in ("*", "all", PICK_ALL_SENTINEL, "__ALL__") for n in profile_names):
        return None
    universe = [p.get("name") for p in listed if p.get("name")]
    return expand_names_with_patterns(universe, set(profile_names))


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------

def summarize_streaming_profiles(bundle):
    if not bundle:
        return []
    customs = [p.get("name") for p in (bundle.get("custom_profiles") or []) if p.get("name")]
    builtins = [f"{p.get('name')} (built-in override)" for p in (bundle.get("overridden_builtins") or []) if p.get("name")]
    return sorted(customs + builtins)


# ---------------------------------------------------------------------------
# Target listing
# ---------------------------------------------------------------------------

def _list_target(target_options) -> Dict[str, Dict[str, Any]]:
    res = cloudinary.api.list_streaming_profiles(**(target_options or {}))
    out = {}
    for p in res.get("data", []) or []:
        name = p.get("name")
        if not name:
            continue
        out[name] = p
    return out


def _fetch_target_detail(name, target_options):
    try:
        return cloudinary.api.get_streaming_profile(name, **(target_options or {})).get("data") or {}
    except Exception as e:
        logger.warning(f"Streaming profiles: failed to fetch target '{name}': {e}")
        return None


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply_streaming_profiles(
    bundle,
    target_options=None,
    dry_run=False,
    force=False,
    profile_names=None,
    mode="create-missing",
    concurrent_workers=DEFAULT_WORKERS,
):
    mode = (mode or "create-missing").lower()
    if mode not in ("create-missing", "upsert", "sync"):
        raise ValueError(f"Unsupported streaming_profiles mode: {mode}")

    if not bundle or not (bundle.get("custom_profiles") or bundle.get("overridden_builtins")):
        logger.info("Streaming profiles: nothing to apply (empty bundle).")
        return True

    custom_profiles = list(bundle.get("custom_profiles") or [])
    overridden_builtins = list(bundle.get("overridden_builtins") or [])

    if profile_names and not any(n in ("*", "all", PICK_ALL_SENTINEL, "__ALL__") for n in profile_names):
        sel_universe = [p["name"] for p in custom_profiles + overridden_builtins if p.get("name")]
        keep = expand_names_with_patterns(sel_universe, set(profile_names))
        custom_profiles = [p for p in custom_profiles if p.get("name") in keep]
        overridden_builtins = [p for p in overridden_builtins if p.get("name") in keep]

    try:
        target_by_name = _list_target(target_options)
    except Exception as e:
        logger.error(f"Streaming profiles: failed to list target: {e}")
        return False

    custom_target_names = {n for n, p in target_by_name.items() if not p.get("predefined")}

    # Plan custom
    cu_create, cu_update, cu_delete = _plan_custom(custom_profiles, target_by_name, custom_target_names, mode, target_options, concurrent_workers)
    # Plan built-ins (only updates ever)
    bi_update = _plan_builtins(overridden_builtins, target_by_name, target_options, concurrent_workers)

    if not (cu_create or cu_update or cu_delete or bi_update):
        logger.info("Streaming profiles: target already matches the desired selection. Nothing to do.")
        return True

    logger.info(f"Streaming profiles plan (mode={mode}):")
    logger.info(
        f"  Custom    -> Create: {len(cu_create)} | Update: {len(cu_update)} | Delete: {len(cu_delete)}"
    )
    logger.info(f"  Built-ins -> Override-update: {len(bi_update)}")

    if not force:
        msg = (
            f"{c('This operation will apply streaming-profile changes to the target environment:', bold=True)}\n"
            f"- custom: "
            f"{c('+' + str(len(cu_create)), fg='green', bold=True)} "
            f"{c('~' + str(len(cu_update)), fg='yellow', bold=True)} "
            f"{c('-' + str(len(cu_delete)), fg='red', bold=True)}\n"
            f"{format_section(c('create', fg='green', bold=True), format_items([p['name'] for p in cu_create]))}"
            f"{format_section(c('update', fg='yellow', bold=True), format_items([p['name'] for p in cu_update]))}"
            f"{format_section(c('delete', fg='red', bold=True), format_items(cu_delete))}"
            f"- built-ins: {c('~' + str(len(bi_update)), fg='yellow', bold=True)} (override-update only; built-ins never created/deleted)\n"
            f"{format_section(c('override-update', fg='yellow', bold=True), format_items([p['name'] for p in bi_update]))}"
            "Continue? (y/N)"
        )
        if not confirm_action(msg):
            logger.info("Stopping.")
            return False

    if dry_run:
        logger.info(
            f"Streaming profiles dry-run: custom +{len(cu_create)} ~{len(cu_update)} -{len(cu_delete)}, "
            f"built-ins ~{len(bi_update)}."
        )
        return True

    return _apply_changes(cu_create, cu_update, cu_delete, bi_update, target_options, mode, concurrent_workers)


def _plan_custom(desired_customs, target_by_name, custom_target_names, mode, target_options, concurrent_workers):
    desired_by_name = {p["name"]: p for p in desired_customs if p.get("name")}

    to_create = []
    to_update = []
    needs_detail = []

    for name, p in desired_by_name.items():
        target_p = target_by_name.get(name)
        if not target_p or target_p.get("predefined"):
            # If the name is a built-in but our snapshot has it as custom,
            # we still create — Cloudinary will reject with 409, which we
            # surface clearly.
            to_create.append(p)
            continue
        if mode == "create-missing":
            continue
        needs_detail.append(name)

    if needs_detail:
        with ThreadPool(min(concurrent_workers, max(1, len(needs_detail)))) as pool:
            details = pool.map(lambda n: (n, _fetch_target_detail(n, target_options)), needs_detail)
        target_details = {n: d for n, d in details if d}
        for name in needs_detail:
            target_p = target_details.get(name)
            if not target_p:
                continue
            if _normalize_for_compare(desired_by_name[name]) != _normalize_for_compare(target_p):
                to_update.append(desired_by_name[name])

    to_delete = []
    if mode == "sync":
        to_delete = sorted(custom_target_names - set(desired_by_name.keys()))

    to_create.sort(key=lambda p: p["name"])
    to_update.sort(key=lambda p: p["name"])
    return to_create, to_update, to_delete


def _plan_builtins(overridden_builtins, target_by_name, target_options, concurrent_workers):
    """
    Built-ins are never created/deleted. We only update them when our captured
    representations differ from what's currently on the target.
    """
    if not overridden_builtins:
        return []

    needs_detail = [p["name"] for p in overridden_builtins if p.get("name") and p["name"] in target_by_name]
    target_details = {}
    if needs_detail:
        with ThreadPool(min(concurrent_workers, max(1, len(needs_detail)))) as pool:
            for n, d in pool.map(lambda n: (n, _fetch_target_detail(n, target_options)), needs_detail):
                if d:
                    target_details[n] = d

    to_update = []
    for p in overridden_builtins:
        name = p.get("name")
        target_p = target_details.get(name)
        if not target_p:
            # Either not present (rare) or unreachable — skip silently in plan.
            continue
        if _normalize_for_compare(p) != _normalize_for_compare(target_p):
            to_update.append(p)

    to_update.sort(key=lambda p: p["name"])
    return to_update


def _apply_changes(cu_create, cu_update, cu_delete, bi_update, target_options, mode, concurrent_workers) -> bool:
    def _create(p):
        try:
            cloudinary.api.create_streaming_profile(
                p["name"],
                display_name=p.get("display_name"),
                representations=_representations_for_apply(p.get("representations")),
                **(target_options or {}),
            )
            logger.info(f"Streaming profiles: created custom '{p['name']}'.")
            return True
        except Exception as e:
            if mode == "create-missing" and _is_already_exists(e):
                logger.debug(f"Streaming profiles: '{p['name']}' already exists (skipped).")
                return True
            logger.error(f"Streaming profiles: failed to create '{p['name']}': {e}")
            return False

    def _update(p, kind="custom"):
        try:
            cloudinary.api.update_streaming_profile(
                p["name"],
                display_name=p.get("display_name"),
                representations=_representations_for_apply(p.get("representations")),
                **(target_options or {}),
            )
            label = "custom" if kind == "custom" else "built-in override"
            logger.info(f"Streaming profiles: updated {label} '{p['name']}'.")
            return True
        except Exception as e:
            logger.error(f"Streaming profiles: failed to update '{p['name']}': {e}")
            return False

    def _delete(name):
        try:
            cloudinary.api.delete_streaming_profile(name, **(target_options or {}))
            logger.info(f"Streaming profiles: deleted custom '{name}'.")
            return True
        except Exception as e:
            logger.error(f"Streaming profiles: failed to delete '{name}': {e}")
            return False

    workers = max(1, min(concurrent_workers, max(len(cu_create), len(cu_update), len(cu_delete), len(bi_update), 1)))
    with ThreadPool(workers) as pool:
        results = []
        if cu_create:
            results.extend(pool.map(_create, cu_create))
        if cu_update:
            results.extend(pool.map(lambda p: _update(p, "custom"), cu_update))
        if cu_delete:
            results.extend(pool.map(_delete, cu_delete))
        if bi_update:
            results.extend(pool.map(lambda p: _update(p, "builtin"), bi_update))

    return all(results) if results else True


def _representations_for_apply(reps):
    """
    Convert our stored representations (list[str]) back into the SDK's
    expected input. The SDK accepts list of dicts/strings and joins with
    `transformation_string` internally.
    """
    if not reps:
        return []
    out = []
    for r in reps:
        if isinstance(r, str):
            out.append({"transformation": r})
        else:
            out.append(r)
    return out


def _is_already_exists(exc) -> bool:
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if status == 409:
        return True
    return "already exists" in (str(exc) or "").lower()


# ---------------------------------------------------------------------------
# Standalone delete
# ---------------------------------------------------------------------------

def delete_streaming_profiles(
    target_options=None,
    dry_run=False,
    force=False,
    profile_names=None,
    allow_revert_builtins=False,
    concurrent_workers=DEFAULT_WORKERS,
):
    requested = list(profile_names or [])
    if not requested:
        logger.info("Streaming profiles: nothing selected for deletion.")
        return True

    try:
        target_by_name = _list_target(target_options)
    except Exception as e:
        logger.error(f"Streaming profiles: failed to list: {e}")
        return False

    universe = list(target_by_name.keys())
    expanded = set()
    if any(n in ("*", "all", PICK_ALL_SENTINEL, "__ALL__") for n in requested):
        expanded |= set(universe)
    else:
        expanded |= expand_names_with_patterns(universe, set(requested))

    to_delete_custom = []
    to_revert_builtin = []
    refused_builtins = []

    for name in sorted(expanded):
        target_p = target_by_name.get(name)
        if not target_p:
            continue
        if target_p.get("predefined"):
            if allow_revert_builtins:
                to_revert_builtin.append(name)
            else:
                refused_builtins.append(name)
        else:
            to_delete_custom.append(name)

    missing = [n for n in requested if n not in universe and n not in ("*", "all", PICK_ALL_SENTINEL, "__ALL__") and not any(ch in n for ch in "*?[")]
    if missing:
        logger.warning(f"Streaming profiles: not found (skipping): {', '.join(missing)}")

    if refused_builtins:
        names_list = ", ".join(refused_builtins)
        logger.error(
            f"Streaming profiles: '{names_list}' is/are built-in profile(s). DELETE will revert "
            "any local overrides. Re-run with --allow-revert-builtins to proceed."
        )
        return False

    if not (to_delete_custom or to_revert_builtin):
        logger.info("Streaming profiles: nothing to delete.")
        return True

    sep = "-" * 60
    logger.info(sep)
    if to_delete_custom:
        logger.info(c(f"Streaming profiles to delete ({len(to_delete_custom)}):", fg="cyan"))
        for n in to_delete_custom:
            logger.info(c(f"  - {n}", fg="yellow"))
    if to_revert_builtin:
        logger.info(c(f"Built-in profiles to revert ({len(to_revert_builtin)}):", fg="cyan"))
        for n in to_revert_builtin:
            logger.info(c(f"  ~ {n}  (revert built-in)", fg="yellow"))
    logger.info(sep)

    if dry_run:
        logger.info(
            f"Streaming profiles dry-run: delete -{len(to_delete_custom)}, revert built-in ~{len(to_revert_builtin)}."
        )
        return True

    if not force:
        action_label = "delete/revert" if to_revert_builtin else "delete"
        if not confirm_action(f"{action_label.capitalize()} {len(to_delete_custom) + len(to_revert_builtin)} profile(s)? (y/N)"):
            logger.info("Stopping.")
            return False

    def _delete(name):
        try:
            cloudinary.api.delete_streaming_profile(name, **(target_options or {}))
            logger.info(f"Streaming profiles: deleted custom '{name}'.")
            return True, name, None
        except Exception as e:
            logger.error(f"Streaming profiles: failed to delete '{name}': {e}")
            return False, name, str(e)

    def _revert(name):
        try:
            cloudinary.api.delete_streaming_profile(name, **(target_options or {}))
            logger.info(f"Streaming profiles: reverted built-in '{name}'.")
            return True, name, None
        except Exception as e:
            logger.error(f"Streaming profiles: failed to revert '{name}': {e}")
            return False, name, str(e)

    workers = max(1, min(concurrent_workers, len(to_delete_custom) + len(to_revert_builtin)))
    with ThreadPool(workers) as pool:
        results = []
        if to_delete_custom:
            results.extend(pool.map(_delete, to_delete_custom))
        if to_revert_builtin:
            results.extend(pool.map(_revert, to_revert_builtin))

    failures = [(n, err) for ok, n, err in results if not ok]
    return not failures


# ---------------------------------------------------------------------------
# Uniform contract
# ---------------------------------------------------------------------------

def export_bundle(*, picks=None, related=None):
    return export_streaming_profiles(profile_names=picks)


def summarize_bundle(bundle):
    return summarize_streaming_profiles(bundle)


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
    return apply_streaming_profiles(
        bundle,
        target_options=target_options,
        dry_run=dry_run,
        force=force,
        profile_names=picks,
        mode=mode,
    )


def delete_items(
    *,
    target_options=None,
    picks=None,
    related=None,
    dry_run=False,
    force=False,
    allow_revert_builtins=False,
):
    return delete_streaming_profiles(
        target_options=target_options,
        dry_run=dry_run,
        force=force,
        profile_names=picks,
        allow_revert_builtins=allow_revert_builtins,
    )
