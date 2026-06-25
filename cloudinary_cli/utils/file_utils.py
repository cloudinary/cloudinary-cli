import os
import stat
import tempfile
from os import walk, path, listdir, rmdir, sep
from os.path import split, relpath, abspath
from pathlib import PurePath

from cloudinary_cli.defaults import logger
from cloudinary_cli.utils.utils import etag

FORMAT_ALIASES = {
    'jpeg': 'jpg',
    'jpe': 'jpg',
    'tif': 'tiff',
    'ps': 'eps',
    'ept': 'eps',
    'eps3': 'eps',
    'j2k': 'jpc',
    'jxr': 'wdp',
    'hdp': 'wdp',
    'm4v': 'mp4',
    'h264': 'mp4',
    'asf': 'wmv',
    'm2v': 'mpeg',
    'm2t': 'ts',
    'm2ts': 'ts',
    'aif': 'aiff',
    'aifc': 'aiff',
    'mka': 'webm',
    'webmda': 'webm',
    'webmdv': 'webm',
    'mp4dv': 'mp4',
    'mp4da': 'mp4',
    'opus': 'ogg',
    'bmp2': 'bmp',
    'bmp3': 'bmp',
    'mpg/3': 'mp3',
    'heif': 'heic',
    'mid': 'midi'
}


def atomic_write(filename, write_fn, mode=None):
    """
    Writes via a temp file in the same directory, then atomically replaces the target, so a
    concurrent reader never sees a half-written file and an interleaved write can't truncate it.

    :param filename: The destination file path.
    :param write_fn: Callable receiving the open temp file object; performs the actual write.
    :param mode:     Final permission bits to set on the file. When given, the temp file is set to
                     this mode before the replace, so the destination is never momentarily wider
                     (mkstemp creates it 0600, so a secret file is never world-readable mid-write).
                     When omitted, normalize to the process umask default like a plain open().
    """
    directory = path.dirname(filename) or "."
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-")
    try:
        with os.fdopen(fd, 'w') as file:
            write_fn(file)
        if mode is not None:
            os.chmod(tmp_path, mode)
        else:
            _apply_umask_permissions(tmp_path)
        os.replace(tmp_path, filename)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _apply_umask_permissions(file):
    # mkstemp creates the temp file as 0600, and os.replace preserves that mode onto the
    # destination. Normalize to the process umask default so output files keep the same
    # permissions a plain open() would have produced; callers needing 0600 (e.g. the config
    # file) tighten it explicitly afterwards.
    current_umask = os.umask(0)
    os.umask(current_umask)
    try:
        os.chmod(file, 0o666 & ~current_umask)
    except OSError as e:
        logger.debug(f"Could not normalize permissions on {file}: {e}")


def walk_dir(root_dir, include_hidden=False):
    all_files = {}
    for root, dirs, files in walk(root_dir):
        if not include_hidden:
            files = [f for f in files if not is_hidden(root, f)]
            dirs[:] = [d for d in dirs if not is_hidden(root, d)]

        relative_path = posix_rel_path(root, root_dir) if root_dir != root else ""
        for file in files:
            full_path = path.join(root, file)
            relative_file_path = "/".join(p for p in [relative_path, file] if p)
            normalized_relative_file_path = normalize_file_extension(relative_file_path)
            all_files[normalized_relative_file_path] = {
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
    splitted = split(posix_rel_path(file_path, parent_path))

    if splitted[0]:
        folder_path = splitted[0].split(sep)

    return "/".join([cloudinary_folder, *folder_path]).strip("/")


def normalize_file_extension(filename: str) -> str:
    """
    Normalizes file extension. Makes it lower case and removes aliases.

    :param filename: The input file name.
    :return: File name with normalized extension.
    """
    filename, extension = os.path.splitext(filename)
    extension = extension[1:].lower()
    extension_alias = FORMAT_ALIASES.get(extension, extension)

    return ".".join([p for p in [filename, extension_alias] if p])


def populate_duplicate_name(filename, index=0):
    """
    Adds index to the filename in order to avoid duplicates.

    :param filename: The file name to modify.
    :param index:   The desired index.
    :return: Modified file name.
    """
    filename, extension = os.path.splitext(filename)
    if index != 0:
        filename = f"{filename} ({index})"

    return ".".join([p for p in [filename, extension[1:]] if p])


def posix_rel_path(end, start) -> str:
    """
    Returns a relative path in posix style on any system.

    :param end: The end path.
    :param start: The start path.
    :return: The Relative path.
    """
    return PurePath(relpath(end, start)).as_posix()
