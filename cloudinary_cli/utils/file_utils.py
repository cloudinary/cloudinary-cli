from os import walk, path, listdir, rmdir, sep
from os.path import split, relpath, abspath

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.utils import etag


def walk_dir(root_dir):
    all_files = {}
    for root, _, files in walk(root_dir):
        relative_path = relpath(root, root_dir) if root_dir != root else ""
        for file in files:
            full_path = path.join(root, file)
            relative_file_path = "/".join(p for p in [relative_path, file] if p)
            all_files[relative_file_path] = {
                "path": full_path,
                "etag": etag(full_path)
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

