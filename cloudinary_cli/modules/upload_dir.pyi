from typing import List, Tuple, Dict, Union
from click import Context

def upload_dir(
    directory: str,
    glob_pattern: str = "**/*",
    include_hidden: bool = False,
    optional_parameter: List[Tuple[str, str]] = None,
    optional_parameter_parsed: List[Tuple[str, str]] = None,
    transformation: Union[str, None] = None,
    folder: str = "",
    folder_mode: Union[str, None] = None,
    preset: Union[str, None] = None,
    concurrent_workers: int = 30,
    exclude_dir_name: bool = False,
    doc: bool = False,
    ctx: Context = None
) -> bool:
    ...
