from os import walk, path, listdir, rmdir, sep
from os.path import split, relpath, abspath

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

