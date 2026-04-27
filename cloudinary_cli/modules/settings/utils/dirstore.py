"""
Directory-mode I/O for snapshots (§4.1).

Layout:
    <dir>/_index.json         envelope only (no component bundles)
    <dir>/smd.json
    <dir>/transformations.json
    <dir>/upload_presets.json
    <dir>/streaming_profiles.json
    <dir>/upload_mappings.json
    <dir>/config.json
"""
from __future__ import annotations

import os
from typing import Dict, Any, Iterable

from cloudinary_cli.utils.json_utils import read_json_from_file, write_json_to_file


_INDEX_FILE = "_index.json"


def write_snapshot_dir(directory: str, snapshot: Dict[str, Any], component_keys: Iterable[str]):
    """
    Split a single-file v2 snapshot into a directory.

    The envelope (every key NOT in `component_keys`) lands in `_index.json`;
    each component bundle goes into its own `<component>.json`.
    """
    os.makedirs(directory, exist_ok=True)
    component_keys = list(component_keys)
    envelope = {k: v for k, v in snapshot.items() if k not in component_keys}
    write_json_to_file(envelope, os.path.join(directory, _INDEX_FILE), indent=2)
    for k in component_keys:
        if k in snapshot and snapshot[k] is not None:
            write_json_to_file(snapshot[k], os.path.join(directory, f"{k}.json"), indent=2)


def read_snapshot_dir(directory: str, component_keys: Iterable[str]) -> Dict[str, Any]:
    """
    Reconstruct a single-file snapshot dict from a directory layout.

    Missing per-component files are simply omitted (matching v2 "additive"
    semantics).
    """
    index_path = os.path.join(directory, _INDEX_FILE)
    if not os.path.exists(index_path):
        raise FileNotFoundError(f"Settings directory '{directory}' is missing '{_INDEX_FILE}'.")
    snapshot = dict(read_json_from_file(index_path) or {})
    for k in component_keys:
        comp_path = os.path.join(directory, f"{k}.json")
        if os.path.exists(comp_path):
            snapshot[k] = read_json_from_file(comp_path)
    return snapshot
