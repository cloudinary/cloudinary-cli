import os
import stat
from os import walk, path, listdir, rmdir, sep
from os.path import split, relpath, abspath

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.utils import etag


def walk_dir(root_dir, include_hidden=False):
    all_files = {}
    for root, dirs, files in walk(root_dir):
        if not include_hidden:
            files = [f for f in files if not is_hidden(root, f)]
            dirs[:] = [d for d in dirs if not is_hidden(root, d)]

        relative_path = relpath(root, root_dir) if root_dir != root else ""
        for file in files:
            full_path = path.join(root, file)
            relative_file_path = "/".join(p for p in [relative_path, file] if p)
            all_files[relative_file_path] = {
                "path": full_path,
                "etag": etag(full_path)
            }
    return all_files


def is_hidden(root, relative_path):
    return is_hidden_path(path.join(root, relative_path))


def is_hidden_path(filepath):
    name = os.path.basename(filepath)
    return name.startswith('.') or has_hidden_attribute(filepath)


def has_hidden_attribute(filepath):
    try:
        st = os.stat(filepath)
    except OSError as e:
        logger.debug(f"Failed getting os.stat for file '{filepath}': {e}")
        return False

    if not hasattr(st, 'st_file_attributes'):  # not a pythonic way, but it's relevant only for windows, no need to try
        return False

    # noinspection PyUnresolvedReferences
    return bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN)


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


def get_destination_folder(cloudinary_folder: str, file_path: str, parent: str = None) -> str:
    """
    :param cloudinary_folder:   Destination folder in Cloudinary
    :param file_path:           Path to the local file
    :param parent:              Parent folder of the directory to upload/sync
    :return:                    Value passed to `folder` when uploading to Cloudinary
    """
    folder_path = []

    parent_path = abspath(parent) if parent else None
    splitted = split(relpath(file_path, parent_path))

    if splitted[0]:
        folder_path = splitted[0].split(sep)

    return "/".join([cloudinary_folder, *folder_path]).strip("/")

