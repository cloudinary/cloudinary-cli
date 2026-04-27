"""
Tiny normalization helpers shared across providers.

Each provider extends these with its own per-component blacklist of
non-roundtrippable / server-computed / noisy keys.
"""
import fnmatch


def strip_dict_keys_deep(obj, forbidden_keys):
    """Recursively remove dict keys from nested dict/list structures."""
    if isinstance(obj, dict):
        return {
            k: strip_dict_keys_deep(v, forbidden_keys)
            for k, v in obj.items()
            if k not in forbidden_keys
        }
    if isinstance(obj, list):
        return [strip_dict_keys_deep(v, forbidden_keys) for v in obj]
    return obj


def sort_string_list_value(value):
    """Sort a comma-separated string or list into a stable tuple for compare."""
    if value is None:
        return None
    if isinstance(value, list):
        return sorted(str(v) for v in value)
    if isinstance(value, str):
        if "," in value:
            return sorted([p.strip() for p in value.split(",") if p.strip()])
        return [value]
    return value


def is_pattern(s):
    return isinstance(s, str) and any(ch in s for ch in ("*", "?", "["))


def expand_names_with_patterns(universe, selected):
    """
    Expand wildcard patterns in `selected` against `universe`.

    Exact matches and wildcard patterns combine into a single set of names.
    """
    selected = set(selected or [])
    if not selected:
        return set()
    patterns = {x for x in selected if is_pattern(x)}
    exact = {x for x in selected if not is_pattern(x)}
    matched = set()
    for p in patterns:
        matched |= set(fnmatch.filter(universe, p))
    return exact | matched


def index_by(items, key):
    """Index a list[dict] by `item[key]`. Items without a value at `key` are skipped."""
    res = {}
    for i in items or []:
        if not isinstance(i, dict):
            continue
        k = i.get(key)
        if k is not None:
            res[k] = i
    return res
