"""
Product environment config provider for settings snapshots.

See settings-design.md §6.6 for the design notes.

`config` is captured by every save (incl. `cloud_name`, `created_at`,
`settings.folder_mode`) but never auto-applied. The Admin API only exposes
read access — writes belong to the Provisioning API and are deferred to a
future release (§13.3).

The bundle's `applicable: false` flag signals to any future writer to
skip apply.
"""
from typing import Dict, Any, List

import cloudinary
import cloudinary.api

from cloudinary_cli.defaults import logger

from ..utils.render import (
    c,
    diff_any,
    format_section,
)


COMPONENT = "config"
PICK_KINDS = ()  # singleton
PICK_ALL_SENTINEL = None


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_config_bundle():
    """
    Read product-environment config (with settings) from the current account.
    """
    logger.info("Exporting product environment config (read-only)...")
    try:
        res = cloudinary.api.config(settings=True)
    except Exception as e:
        logger.warning(f"Config: failed to fetch product environment config: {e}")
        return {"settings": {}, "applicable": False}

    settings = _project_config(res)
    return {"settings": settings, "applicable": False}


def _project_config(res) -> Dict[str, Any]:
    """Project the SDK response into our snapshot form."""
    if not isinstance(res, dict):
        return {}
    out = {}
    for k in ("cloud_name", "created_at"):
        if k in res:
            out[k] = res.get(k)
    if "settings" in res and isinstance(res["settings"], dict):
        out["settings"] = res["settings"]
    return out


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------

def summarize_config_bundle(bundle) -> List[str]:
    if not bundle or not bundle.get("settings"):
        return []
    s = bundle["settings"]
    lines = []
    cloud_name = s.get("cloud_name")
    if cloud_name:
        lines.append(f"cloud_name={cloud_name}")
    folder_mode = (s.get("settings") or {}).get("folder_mode")
    if folder_mode:
        lines.append(f"folder_mode={folder_mode}")
    return lines


# ---------------------------------------------------------------------------
# Apply (refused)
# ---------------------------------------------------------------------------

def apply_config_bundle(bundle, target_options=None, **_):
    """Config is captured for diffing only; refuse apply with a clear warning."""
    logger.warning(
        "Config is captured for diffing only and is never applied. "
        "Use `cld settings diff --component config` to see drift; change values "
        "in the Console or via the Provisioning API."
    )
    return True


# ---------------------------------------------------------------------------
# Diff (the only restore-time interaction)
# ---------------------------------------------------------------------------

def diff_config_bundle(bundle, target_options=None) -> bool:
    """
    Compare the bundle's captured config against the live product-environment
    config. Returns True iff there's no drift.
    """
    if not bundle or not bundle.get("settings"):
        logger.info("Config: snapshot has no captured config — skipping.")
        return True

    try:
        live = cloudinary.api.config(settings=True, **(target_options or {}))
    except Exception as e:
        logger.error(f"Config: failed to fetch live config for diff: {e}")
        return False

    desired = bundle["settings"]
    target = _project_config(live)

    diffs = diff_any(desired, target, path="$.config", max_diffs=200)
    if not diffs:
        logger.info(c("Config: no drift detected.", fg="green"))
        return True

    logger.info(c(f"Config: {len(diffs)} drift line(s) detected:", fg="yellow", bold=True))
    for d in diffs:
        if "present in desired only" in d:
            logger.info(c(f"  + {d}", fg="green"))
        elif "present in target only" in d:
            logger.info(c(f"  - {d}", fg="red"))
        elif " != " in d:
            logger.info(c(f"  ~ {d}", fg="yellow"))
        else:
            logger.info(f"  • {d}")
    logger.info(
        "Note: config drift is read-only here. Change values in the Console or "
        "via the Provisioning API."
    )
    return False


# ---------------------------------------------------------------------------
# Uniform contract
# ---------------------------------------------------------------------------

def export_bundle(*, picks=None, related=None):
    return export_config_bundle()


def summarize_bundle(bundle):
    return summarize_config_bundle(bundle)


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
    return apply_config_bundle(bundle, target_options=target_options)
