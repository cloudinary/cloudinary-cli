"""
Snapshot envelope: v2 schema with v1 backwards-compatible loader.

See settings-design.md §4.

Envelope fields (in addition to component bundles):
    schema_version   : int          (2)
    type             : str          ("settings_snapshot")
    name             : str
    lineage          : str (UUID)   stable across copies/renames
    serial           : int          bumps each save under the same lineage
    created_at       : ISO8601 str
    writer           : { cli_version, sdk_version, user }
    source           : { cloud_name, config_settings? }
    components       : list[str]
    selection        : { components, picks }
    metadata         : { notes, tags }
    fingerprints     : { <component>: "sha256:..." }
    checksum         : "sha256:..." over canonical JSON of components+sections
"""
from __future__ import annotations

import getpass
import hashlib
import json
import os
import socket
import uuid
from datetime import datetime, timezone
from typing import Optional, Iterable, Dict, Any, List

import cloudinary

from cloudinary_cli.version import __version__ as _CLI_VERSION


SCHEMA_VERSION = 2
SNAPSHOT_TYPE = "settings_snapshot"


def _sdk_version() -> str:
    """
    Best-effort SDK version detection.

    The Cloudinary Python SDK exposes VERSION at the package level.
    """
    return getattr(cloudinary, "VERSION", "") or ""


def _user_string() -> str:
    """`<user>@<host>` for forensics. Never identity beyond the local machine."""
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
    try:
        host = socket.gethostname()
    except Exception:
        host = "unknown"
    return f"{user}@{host}"


def make_writer() -> Dict[str, str]:
    return {
        "cli_version": _CLI_VERSION,
        "sdk_version": _sdk_version(),
        "user": _user_string(),
    }


def _canonical_json(value) -> str:
    """Stable canonical JSON used for fingerprints and checksums."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprint_component(bundle) -> str:
    """sha256 over the canonical JSON of one component bundle."""
    return _sha256(_canonical_json(bundle if bundle is not None else {}))


def compute_fingerprints(component_bundles: Dict[str, Any]) -> Dict[str, str]:
    return {comp: fingerprint_component(bundle) for comp, bundle in component_bundles.items() if bundle is not None}


def compute_checksum(snapshot: Dict[str, Any], component_keys: Iterable[str]) -> str:
    """
    Checksum over canonical JSON of components+sections; envelope excluded.

    `snapshot` may already include the envelope; we only consume the listed
    `component_keys` to produce the checksum.
    """
    payload = {k: snapshot.get(k) for k in component_keys if k in snapshot}
    return _sha256(_canonical_json(payload))


def make_envelope(
    *,
    name: str,
    cloud_name: Optional[str],
    components: List[str],
    selection: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    lineage: Optional[str] = None,
    serial: int = 1,
    config_settings: Optional[Dict[str, Any]] = None,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build the v2 envelope dict (without component bundles).

    Callers fill in component sections, then call `finalize_envelope()` to
    add `fingerprints` + `checksum`.
    """
    env: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "type": SNAPSHOT_TYPE,
        "name": name,
        "lineage": lineage or str(uuid.uuid4()),
        "serial": int(serial),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "writer": make_writer(),
        "source": {"cloud_name": cloud_name},
        "components": list(components),
        "selection": selection or {"components": list(components), "picks": []},
        "metadata": metadata or {"notes": None, "tags": []},
    }
    if config_settings:
        env["source"]["config_settings"] = config_settings
    return env


def finalize_envelope(snapshot: Dict[str, Any], component_keys: Iterable[str]) -> Dict[str, Any]:
    """
    Compute and attach `fingerprints` and `checksum` for the listed components.

    Mutates and returns `snapshot`.
    """
    component_keys = list(component_keys)
    component_bundles = {k: snapshot.get(k) for k in component_keys if k in snapshot}
    snapshot["fingerprints"] = compute_fingerprints(component_bundles)
    snapshot["checksum"] = compute_checksum(snapshot, component_keys)
    return snapshot


# ---------------------------------------------------------------------------
# Loader (v1 backcompat)
# ---------------------------------------------------------------------------

def load_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a loaded snapshot to the v2 envelope shape.

    v1 (smd-only) snapshots are upgraded on read: missing envelope fields
    are filled with `None`, the component list is inferred from present keys,
    and a fresh lineage/serial is *not* invented (stays None) so we can tell
    older files apart later.
    """
    if not isinstance(snapshot, dict):
        return snapshot

    schema = snapshot.get("schema_version")
    if schema in (None, 1):
        # Soft upgrade. Don't mutate the underlying file; produce an in-memory
        # v2 view that callers can use uniformly.
        upgraded = dict(snapshot)
        upgraded.setdefault("schema_version", 1)
        upgraded.setdefault("type", SNAPSHOT_TYPE)
        upgraded.setdefault("lineage", None)
        upgraded.setdefault("serial", None)
        upgraded.setdefault("writer", None)
        upgraded.setdefault("metadata", {"notes": None, "tags": []})
        if "selection" not in upgraded:
            upgraded["selection"] = {
                "components": upgraded.get("components") or [],
                "picks": [],
            }
        # v1 used a `types` field for SMD-only; map to `components` if present.
        if "components" not in upgraded and "types" in upgraded:
            upgraded["components"] = upgraded.get("types") or []
        return upgraded

    return snapshot


def previous_serial_for_lineage(existing_path: Optional[str]) -> tuple:
    """
    Inspect an existing snapshot file and return (lineage, serial) so callers
    can bump serial on overwrite. Returns (None, 0) if file missing or unparseable.
    """
    if not existing_path or not os.path.exists(existing_path):
        return None, 0
    try:
        with open(existing_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("lineage"), int(data.get("serial") or 0)
    except Exception:
        return None, 0


def collect_component_bundles(snapshot: Dict[str, Any], component_keys: Iterable[str]) -> Dict[str, Any]:
    """Return a dict of present component bundles."""
    return {k: snapshot.get(k) for k in component_keys if k in snapshot and snapshot.get(k) is not None}
