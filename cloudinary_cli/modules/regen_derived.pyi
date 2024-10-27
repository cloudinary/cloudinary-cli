from typing import Optional, List, Tuple
from click import Command

def regen_derived(
    trans_str: str,
    eager_notification_url: Optional[str] = None,
    eager_async: bool = False,
    auto_paginate: bool = False,
    force: bool = False,
    max_results: int = 10,
    concurrent_workers: int = 30
) -> bool: ...

def normalise_trans_name(trans_name: str) -> str: ...

# Assuming other imported functions and modules are already typed
