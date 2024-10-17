from typing import Optional
import click
from click import Context

def cli(
    config: Optional[str] = None,
    config_saved: Optional[str] = None,
    ctx: Optional[Context] = None
) -> bool:
    ...
