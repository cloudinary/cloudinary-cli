from typing import Tuple, List, Optional

def make(
    template: Tuple[str, ...],
    list_languages: bool = False,
    list_templates: bool = False
) -> bool: ...

def _handle_language_and_template(
    language_and_template: Optional[Tuple[str, ...]]
) -> Tuple[str, List[str]]: ...
