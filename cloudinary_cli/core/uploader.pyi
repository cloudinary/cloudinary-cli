# cloudinary_cli/stubs/uploader.pyi

from typing import Tuple, List, Any
from click import Command

def uploader(
    params: Tuple[str, ...],
    optional_parameter: List[Tuple[str, str]],
    optional_parameter_parsed: List[Tuple[str, str]],
    ls: bool,
    save: str | None,
    doc: bool
) -> Any: ...
