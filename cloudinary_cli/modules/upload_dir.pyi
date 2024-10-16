# from typing import Dict, List, Tuple, Any, Optional
# from pathlib import Path

# def upload_dir(directory: str, glob_pattern: str = "**/*", include_hidden: bool = False,
#                optional_parameter: Optional[List[Tuple[str, str]]] = None,
#                optional_parameter_parsed: Optional[List[Tuple[str, str]]] = None,
#                transformation: Optional[str] = None, folder: str = "",
#                folder_mode: Optional[str] = None, preset: Optional[str] = None,
#                concurrent_workers: int = 30, exclude_dir_name: bool = False, 
#                doc: bool = False) -> bool:
#     items: Dict[str, Any]
#     skipped: Dict[str, Any]
#     dir_to_upload: Path
#     parent: str
#     contents_str: str
#     defaults: Dict[str, Any]
#     upload_dir_options: Dict[str, Optional[str]]
#     options: Dict[str, Any]
#     uploads: List[Tuple[Path, Dict[str, Any], Dict[str, Any], Dict[str, Any]]]
#     ...
