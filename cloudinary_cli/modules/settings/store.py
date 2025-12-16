import os
from os.path import abspath, dirname, join as path_join

import cloudinary

from cloudinary_cli.defaults import CLOUDINARY_CLI_CONFIG_FILE, CLOUDINARY_HOME, logger


SETTINGS_STORE_DIRNAME = "settings"


def get_settings_store_root():
    # Keep settings alongside the CLI config file / home folder conventions.
    base = dirname(CLOUDINARY_CLI_CONFIG_FILE) if CLOUDINARY_CLI_CONFIG_FILE else abspath(CLOUDINARY_HOME)
    return abspath(path_join(base, SETTINGS_STORE_DIRNAME))


def ensure_settings_store_dirs():
    root = get_settings_store_root()
    os.makedirs(root, exist_ok=True)
    return root


def resolve_cloud_name_or_current(cloud_name=None):
    if cloud_name:
        return cloud_name
    current = cloudinary.config().cloud_name
    if not current:
        raise Exception("No Cloudinary configuration found (cloud_name is missing).")
    return current


def get_settings_store_snapshot_path(cloud_name, name):
    root = ensure_settings_store_dirs()
    cloud_dir = path_join(root, cloud_name)
    os.makedirs(cloud_dir, exist_ok=True)
    return path_join(cloud_dir, f"{name}.json")


def list_settings_store_entries(cloud_name=None):
    root = ensure_settings_store_dirs()
    entries = []

    if cloud_name:
        clouds = [cloud_name]
    else:
        try:
            clouds = sorted([d for d in os.listdir(root) if os.path.isdir(path_join(root, d))])
        except FileNotFoundError:
            clouds = []

    for c in clouds:
        cloud_dir = path_join(root, c)
        if not os.path.isdir(cloud_dir):
            continue
        for fn in sorted(os.listdir(cloud_dir)):
            if not fn.endswith(".json"):
                continue
            entries.append({
                "cloud_name": c,
                "name": fn[:-5],
                "path": path_join(cloud_dir, fn),
            })

    return entries


def delete_settings_store_snapshot(cloud_name, name):
    snapshot_path = get_settings_store_snapshot_path(cloud_name, name)
    if not os.path.exists(snapshot_path):
        return False
    try:
        os.remove(snapshot_path)
    except Exception as e:
        logger.error(f"Failed deleting '{snapshot_path}': {e}")
        return False
    return True
