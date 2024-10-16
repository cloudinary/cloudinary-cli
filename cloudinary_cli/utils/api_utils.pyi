
from typing import Any, Dict, List, Optional, Tuple


PAGINATION_MAX_RESULTS = 500

_cursor_fields: Dict[str, str] = {"resource": "derived_next_cursor"}


def query_cld_folder(folder: str, folder_mode: str) -> Dict[str, Any]:
    ...

def cld_folder_exists(folder: str) -> bool:
    ...

def _display_path(asset: Dict[str, Any]) -> str:
    ...

def _relative_display_path(asset: Dict[str, Any], folder: str) -> str:
    ...

def _relative_path(asset: Dict[str, Any], folder: str) -> str:
    ...

def regen_derived_version(
    public_id: str, delivery_type: str, res_type: str,
    eager_trans: Optional[Any], eager_async: bool,
    eager_notification_url: Optional[str]
) -> None:
    ...

def upload_file(file_path: str, options: Dict[str, Any], uploaded: Optional[Dict[str, Any]] = None, failed: Optional[Dict[str, Any]] = None) -> None:
    ...

def get_default_upload_options(folder_mode: str) -> Dict[str, Any]:
    ...

def get_destination_folder_options(file: str, remote_dir: str, folder_mode: str, parent: Optional[str] = None) -> Dict[str, Any]:
    ...

def download_file(remote_file: Dict[str, Any], local_path: str, downloaded: Optional[Dict[str, str]] = None, failed: Optional[Dict[str, str]] = None) -> None:
    ...

def asset_source(asset_details: Dict[str, Any]) -> str:
    ...

def get_folder_mode() -> str:
    ...

def call_api(func: Any, args: List[Any], kwargs: Dict[str, Any]) -> Any:
    ...

def handle_command(
    params: List[str],
    optional_parameter: List[str],
    optional_parameter_parsed: List[Tuple[str, Any]],
    module: Any,
    module_name: str
) -> bool:
    ...

def handle_api_command(
    params: List[str],
    optional_parameter: List[str],
    optional_parameter_parsed: List[Tuple[str, Any]],
    ls: bool,
    save: Optional[str],
    doc: bool,
    doc_url: Optional[str],
    api_instance: Any,
    api_name: str,
    auto_paginate: bool = False,
    force: bool = False,
    filter_fields: Optional[List[str]] = None,
    return_data: bool = False
) -> Optional[Any]:
    ...

def handle_auto_pagination(
    res: Dict[str, Any],
    func: Any,
    args: List[Any],
    kwargs: Dict[str, Any],
    force: bool,
    filter_fields: Optional[List[str]]
) -> Dict[str, Any]:
    ...
