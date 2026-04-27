"""
Shared rendering helpers used by every settings provider.

Extracted from `providers/smd.py` so that all providers produce identical-
looking plans, confirms, and per-item diffs (see settings-design.md §3.1).

Public surface:
    - c(s, fg=None, bold=False, dim=False) -> str
    - format_items(items, indent="  ", bullet="- ", max_items=20) -> str
    - format_section(label, body, none_value="(none)", indent="  ") -> str
    - colorize_diff_line(line) -> str
    - format_updates_with_diffs(items, diffs_by_item, indent="  ", bullet="- ", max_items=20) -> str
    - diff_any(a, b, path="$", max_diffs=200) -> list[str]
    - compact(value, max_len=240) -> str
    - debug_log_diff(kind, identifier, desired, target, max_lines=200) -> None
"""
from __future__ import annotations

import json
import logging

import click

from cloudinary_cli.defaults import logger


def _stdout_isatty() -> bool:
    try:
        return click.get_text_stream("stdout").isatty()
    except Exception:
        return False


def c(s, fg=None, bold=False, dim=False) -> str:
    """
    Color-aware wrapper around click.style.

    Returns the string unchanged when stdout is not a TTY (so logs and CI
    output stay clean).
    """
    if not _stdout_isatty():
        return s
    return click.style(s, fg=fg, bold=bold, dim=dim)


def colorize_diff_line(line: str) -> str:
    """
    Colorize a diff line emitted by `diff_any`. Heuristics:
        '... present in desired only' -> green +
        '... present in target only'  -> red -
        '... A != B'                  -> yellow ~
        otherwise                     -> dim bullet
    """
    if "present in desired only" in line:
        return f"{c('+', fg='green', bold=True)} {c(line, fg='green', dim=True)}"
    if "present in target only" in line:
        return f"{c('-', fg='red', bold=True)} {c(line, fg='red', dim=True)}"
    if " != " in line:
        return f"{c('~', fg='yellow', bold=True)} {c(line, fg='yellow')}"
    return f"{c('•', fg='white', dim=True)} {line}"


def format_items(items, indent: str = "  ", bullet: str = "- ", max_items: int = 20) -> str:
    """
    Render a flat list as bullets, truncating with a trailing summary line.
    """
    if not items:
        return f"{indent}(none)"
    shown = list(items)[:max_items]
    lines = [f"{indent}{bullet}{x}" for x in shown]
    if len(items) > max_items:
        lines.append(f"{indent}{bullet}… (+{len(items) - max_items} more)")
    return "\n".join(lines)


def format_updates_with_diffs(
    display_items,
    diff_lines_by_display_item,
    indent: str = "  ",
    bullet: str = "- ",
    max_items: int = 20,
) -> str:
    """
    Render an update list with optional per-item diff lines (debug-mode aid).
    `diff_lines_by_display_item[item]` -> list[str] of diff lines from `diff_any`.
    """
    if not display_items:
        return f"{indent}(none)"
    shown = list(display_items)[:max_items]
    lines = []
    for item in shown:
        lines.append(f"{indent}{bullet}{item}")
        dl = diff_lines_by_display_item.get(item) or []
        for d in dl:
            lines.append(f"{indent}    {colorize_diff_line(d)}")
    if len(display_items) > max_items:
        lines.append(f"{indent}{bullet}… (+{len(display_items) - max_items} more)")
    return "\n".join(lines)


def format_section(label: str, body: str, none_value: str = "(none)", indent: str = "  ") -> str:
    """
    Render a labeled section.

    '<indent><label>: (none)'
        when body collapses to none_value, else
    '<indent><label>:\\n<body>\\n'
    """
    body_str = body or ""
    if body_str.strip() == none_value:
        return f"{indent}{label}: {none_value}\n"
    return f"{indent}{label}:\n{body_str}\n"


def compact(v, max_len: int = 240) -> str:
    """Compact a value into a single-line string for diff/debug output."""
    try:
        s = json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        s = str(v)
    s = s.replace("\n", "\\n")
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s


def diff_any(a, b, path: str = "$", max_diffs: int = 200, list_key_fn=None):
    """
    Best-effort, human-readable diff between two JSON-ish structures.

    When comparing list-of-dicts, `list_key_fn(entry)` (if provided) is used
    to align entries; otherwise we fall back to index alignment. The default
    for SMD-style datasource entries is provided by callers.
    """
    diffs = []

    def add(msg):
        if len(diffs) < max_diffs:
            diffs.append(msg)

    if a == b:
        return diffs

    if isinstance(a, dict) and isinstance(b, dict):
        a_keys = set(a.keys())
        b_keys = set(b.keys())
        for k in sorted(a_keys - b_keys):
            add(f"{path}.{k}: present in desired only")
        for k in sorted(b_keys - a_keys):
            add(f"{path}.{k}: present in target only")
        for k in sorted(a_keys & b_keys):
            if len(diffs) >= max_diffs:
                break
            av, bv = a.get(k), b.get(k)
            if av == bv:
                continue
            if isinstance(av, (dict, list)) and isinstance(bv, (dict, list)):
                diffs.extend(diff_any(av, bv, path=f"{path}.{k}", max_diffs=max_diffs - len(diffs), list_key_fn=list_key_fn))
            else:
                add(f"{path}.{k}: {compact(av)} != {compact(bv)}")
        return diffs

    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            add(f"{path}: list length {len(a)} != {len(b)}")
        if list_key_fn and all(isinstance(x, dict) for x in a) and all(isinstance(x, dict) for x in b):
            a_map = {(list_key_fn(x) or str(i)): x for i, x in enumerate(a)}
            b_map = {(list_key_fn(x) or str(i)): x for i, x in enumerate(b)}
            keys = sorted(set(a_map.keys()) | set(b_map.keys()))
            for k in keys:
                if len(diffs) >= max_diffs:
                    break
                if k not in a_map:
                    add(f"{path}[{k}]: present in target only")
                elif k not in b_map:
                    add(f"{path}[{k}]: present in desired only")
                else:
                    if a_map[k] != b_map[k]:
                        diffs.extend(diff_any(a_map[k], b_map[k], path=f"{path}[{k}]", max_diffs=max_diffs - len(diffs), list_key_fn=list_key_fn))
            return diffs

        for i in range(min(len(a), len(b))):
            if len(diffs) >= max_diffs:
                break
            if a[i] != b[i]:
                diffs.extend(diff_any(a[i], b[i], path=f"{path}[{i}]", max_diffs=max_diffs - len(diffs), list_key_fn=list_key_fn))
        return diffs

    add(f"{path}: {compact(a)} != {compact(b)}")
    return diffs


def debug_log_diff(kind: str, identifier: str, desired, target, max_lines: int = 200, list_key_fn=None) -> None:
    """Emit a structured diff under DEBUG only; cheap no-op otherwise."""
    if not logger.isEnabledFor(logging.DEBUG):
        return
    diffs = diff_any(desired, target, path="$", max_diffs=max_lines, list_key_fn=list_key_fn)
    if not diffs:
        return
    logger.debug(f"{kind} diff for {identifier}:")
    for line in diffs[:max_lines]:
        logger.debug(f"  {line}")
    if len(diffs) > max_lines:
        logger.debug(f"  … (+{len(diffs) - max_lines} more)")


def format_plan_header(component_label: str, counts: dict, label_lbls=None) -> str:
    """
    Render a per-component header like:

        <component_label>:
        - items:   +3 ~1 -2

    `counts` is a dict of section_name -> dict(create=int, update=int, delete=int).
    """
    if not label_lbls:
        label_lbls = ("create", "update", "delete")
    create_lbl, update_lbl, delete_lbl = label_lbls
    lines = [c(f"{component_label}:", bold=True)]
    width = max((len(name) for name in counts.keys()), default=0)
    for section, vals in counts.items():
        n_c = vals.get("create", 0)
        n_u = vals.get("update", 0)
        n_d = vals.get("delete", 0)
        lines.append(
            f"- {section.ljust(width)}: "
            f"{c('+' + str(n_c), fg='green', bold=True)} "
            f"{c('~' + str(n_u), fg='yellow', bold=True)} "
            f"{c('-' + str(n_d), fg='red', bold=True)}"
        )
    return "\n".join(lines)
