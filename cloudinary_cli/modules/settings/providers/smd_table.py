from cloudinary_cli.utils.utils import mid_trim


def render_smd_fields_table(field_rows, max_total=120):
    """
    Render SMD field rows as a compact table (<= max_total chars per line).
    Values are middle-trimmed when needed.

    Returns a list of lines, without trailing newlines.
    """
    if not field_rows:
        return []

    ext_w, type_w, ds_w = _compute_table_widths(field_rows, max_total=max_total)
    lines = []
    h_ext = mid_trim("external_id", ext_w)
    h_type = mid_trim("type", type_w)
    h_ds = mid_trim("datasource_values", ds_w)
    lines.append(f"    {h_ext:<{ext_w}}  {h_type:<{type_w}}  {h_ds}")

    for r in field_rows:
        ext = mid_trim(r.get("external_id", ""), ext_w)
        typ = mid_trim(short_type(r.get("type", "")), type_w)
        ds = mid_trim(r.get("datasource_values", ""), ds_w)
        lines.append(f"    {ext:<{ext_w}}  {typ:<{type_w}}  {ds}")

    return lines


def short_type(raw_type):
    """
    Map SMD field type strings to short codes for display.
    """
    t = (raw_type or "").lower()
    if t == "integer":
        return "int"
    if t == "string":
        return "str"
    if not t:
        return ""
    return t[:4]


def format_datasource_values(values, max_items=8, max_len=120):
    """
    Compact datasource values for display:
    - show up to max_items values
    - include total count when truncated
    - cap total string length to max_len
    """
    total = len(values)
    if total == 0:
        return ""

    shown = values[:max_items]
    s = ", ".join(shown)
    if total > max_items:
        s = f"{s}, … (+{total - max_items})"

    if len(s) > max_len:
        s = s[: max_len - 1] + "…"

    return s


def _compute_table_widths(field_rows, max_total=120):
    """
    Compute column widths so that:
      indent(4) + ext + 2 + type + 2 + ds <= max_total
    """
    indent = 4
    sep = 2
    min_ext = len("external_id")
    # Type is rendered as a short code in the table (up to 4 chars).
    min_type = 4
    min_ds = 20

    max_ext = max(min_ext, *(len(r.get("external_id", "")) for r in field_rows)) if field_rows else min_ext

    ext_w = min(max_ext, 40)
    type_w = min_type

    ds_w = max_total - indent - ext_w - sep - type_w - sep
    if ds_w < min_ds:
        # Reduce ext first, but don't go below header.
        need = min_ds - ds_w
        reducible_ext = max(0, ext_w - min_ext)
        take = min(need, reducible_ext)
        ext_w -= take
        need -= take

        ds_w = max_total - indent - ext_w - sep - type_w - sep
        ds_w = max(ds_w, min_ds)

    return ext_w, type_w, ds_w
