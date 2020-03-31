from os import walk, path, listdir, rmdir

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.utils import etag


def walk_dir(root_dir):
    all_files = {}
    for root, _, files in walk(root_dir):
        for file in files:
            all_files[path.splitext(path.join(root, file)[len(root_dir) + 1:])[0]] = {
                "path": path.join(root, file),
                "etag": etag(path.join(root, file))
            }
    return all_files


def delete_empty_dirs(root, remove_root=False):
    if not path.isdir(root):
        return

    files = listdir(root)
    if len(files):
        for f in files:
            full_path = path.join(root, f)
            if path.isdir(full_path):
                delete_empty_dirs(full_path, True)

    files = listdir(root)
    if len(files) == 0 and remove_root:
        logger.debug(f"Removing empty folder '{root}'")
        rmdir(root)
