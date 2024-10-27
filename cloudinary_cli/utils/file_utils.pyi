from typing import Dict, Optional, Union, Any

FORMAT_ALIASES: Dict[str, str] = {
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

def walk_dir(root_dir: str, include_hidden: bool = False) -> Dict[str, Dict[str, Union[str, Any]]]:
    ...

def is_hidden(root: str, relative_path: str) -> bool:
    ...

def is_hidden_path(filepath: str) -> bool:
    ...

def has_hidden_attribute(filepath: str) -> bool:
    ...

def delete_empty_dirs(root: str, remove_root: bool = False) -> None:
    ...

def get_destination_folder(cloudinary_folder: str, file_path: str, parent: Optional[str] = None) -> str:
    ...

def normalize_file_extension(filename: str) -> str:
    ...

def populate_duplicate_name(filename: str, index: int = 0) -> str:
    ...

def posix_rel_path(end: str, start: str) -> str:
    ...
