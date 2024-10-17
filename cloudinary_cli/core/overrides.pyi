# cloudinary_cli/stubs/overrides.pyi

from typing import Any, Tuple, Optional
from click import Context, Command

# Define a type for the `resolve_command` method
def resolve_command(self: Any, ctx: Context, args: list[str]) -> Tuple[str, Optional[Command], list[str]]:
    ...

# Define a type for the `upload` function
def upload(file: Any, **options: Any) -> Any: 
    ...

# Define a type for the `cloudinary_url` function
def cloudinary_url(source: Any, **options: Any) -> Any:
    ...
