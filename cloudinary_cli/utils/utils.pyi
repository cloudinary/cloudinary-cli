from typing import Any, Dict, List, Optional, Tuple, Union, Set

not_callable = (
    'is_appengine_sandbox', 'call_tags_api', 'call_context_api', 
    'call_cacheable_api', 'call_api', 'call_metadata_api', 
    'call_json_api', 'only', 'transformation_string', 
    'account_config', 'reset_config', 'upload_large_part', 
    'upload_image', 'upload_resource'
)

BLOCK_SIZE = 65536


class ConfigurationError(Exception):
    pass


def etag(fi: str) -> str:
    ...

def is_builtin_class_instance(obj: Any) -> bool:
    ...

def get_help_str(module: Any, block_list: Tuple[str, ...] = (), allow_list: Tuple[str, ...] = ()) -> str:
    ...

def print_api_help(api: Any, block_list: Tuple[str, ...] = not_callable, allow_list: Tuple[str, ...] = ()) -> None:
    ...

def log_exception(e: Exception, message: Optional[str] = None, debug_message: Optional[str] = None) -> None:
    ...

def load_template(language: str, template_name: str) -> Union[str, bool]:
    ...

def parse_option_value(value: Any) -> Any:
    ...

def parse_args_kwargs(func: Any, params: Optional[List[str]] = None, kwargs: Optional[Dict[str, Any]] = None) -> Tuple[List[Any], Dict[str, Any]]:
    ...

def remove_string_prefix(string: str, prefix: str) -> str:
    ...

def invert_dict(d: Dict[Any, Any]) -> Dict[Any, Any]:
    ...

def write_json_list_to_csv(json_list: List[Dict[str, Any]], filename: str, fields_to_keep: Tuple[str, ...] = ()) -> None:
    ...

def run_tasks_concurrently(func: Any, tasks: List[Tuple], concurrent_workers: int) -> None:
    ...

def confirm_action(message: str = "Continue? (y/N)") -> bool:
    ...

def get_user_action(message: str, options: Dict[str, Any]) -> Optional[Any]:
    ...

def get_command_params(
        params: List[str],
        optional_parameter: List[str],
        optional_parameter_parsed: List[Tuple[str, str]],
        module: Any,
        module_name: str) -> Tuple[Any, List[Any], Dict[str, Any]]:
    ...

def group_params(*params: List[Tuple[str, Any]]) -> Dict[str, Any]:
    ...

def print_help_and_exit() -> None:
    ...

def whitelist_keys(data: List[Dict[str, Any]], keys: List[str]) -> List[Dict[str, Any]]:
    ...

def merge_responses(all_res: Dict[str, Any], paginated_res: Dict[str, Any], fields_to_keep: Optional[List[str]] = None, pagination_field: Optional[str] = None) -> Tuple[Dict[str, Any], str]:
    ...

def normalize_list_params(params: List[str]) -> List[str]:
    ...

def chunker(seq: List[Any], size: int) -> Any:
    ...

def duplicate_values(items: Dict[str, Any], value_key: str, key_of_interest: Optional[str] = None) -> Dict[Any, Set[Any]]:
    ...
