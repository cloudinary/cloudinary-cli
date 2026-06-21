"""
Snapshot envelope: v1 schema.

See settings-design.md §4.

Envelope fields (in addition to component bundles):
    schema_version   : int          (1)
    type             : str          ("settings_snapshot")
    name             : str
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
from datetime import datetime, timezone
from typing import Optional, Iterable, Dict, Any, List

import click
import cloudinary

from cloudinary_cli.version import __version__ as _CLI_VERSION


SCHEMA_VERSION = 1
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
    config_settings: Optional[Dict[str, Any]] = None,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build the v1 envelope dict (without component bundles).

    Callers fill in component sections, then call `finalize_envelope()` to
    add `fingerprints` + `checksum`.
    """
    env: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "type": SNAPSHOT_TYPE,
        "name": name,
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


def load_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate a loaded snapshot's envelope shape and return it unchanged.

    Rejects any `schema_version` other than the current one with a
    `click.UsageError`. There is no soft-upgrade path.
    """
    if not isinstance(snapshot, dict):
        return snapshot

    schema = snapshot.get("schema_version")
    if schema != SCHEMA_VERSION:
        raise click.UsageError(
            "This snapshot was written by an older or newer CLI: "
            f"schema_version={schema!r}; expected {SCHEMA_VERSION}."
        )
    return snapshot


def collect_component_bundles(snapshot: Dict[str, Any], component_keys: Iterable[str]) -> Dict[str, Any]:
    """Return a dict of present component bundles."""
    return {k: snapshot.get(k) for k in component_keys if k in snapshot and snapshot.get(k) is not None}
