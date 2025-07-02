import json
from cloudinary.utils import build_array


def parse_aggregate(agg_input):
    """
    Parses an aggregator definition or list of definitions into structured aggregator objects.

    Accepts:
      - Full JSON (if a string starts with '{')
      - Transformation-style string (if a string contains ':')
      - Simple aggregate string
      - A list (or tuple) of any of the above

    :param agg_input: Aggregator definition(s) as a string or list of strings.
    :type agg_input: str or list or dict
    :return: List of parsed aggregator objects.
    :rtype: list
    """
    agg_list = build_array(agg_input)
    parsed_aggregators = []

    for agg in agg_list:
        if isinstance(agg, str):
            s = agg.strip()

            if s.startswith("{"):
                parsed = parse_json_aggregate(s)
            else:
                parsed = parse_aggregate_string(s)

            parsed_aggregators.append(parsed)
        else:
            parsed_aggregators.append(agg)

    return parsed_aggregators


def parse_json_aggregate(s):
    """
    Parses a JSON aggregator string.

    :param s: JSON aggregator string.
    :type s: str
    :return: Parsed aggregator object.
    :rtype: dict
    :raises: ValueError if JSON is invalid or missing the required 'type' key.
    """
    try:
        agg_obj = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError("Invalid JSON provided for aggregate: " + str(e))

    if not (isinstance(agg_obj, dict) and "type" in agg_obj):
        raise ValueError("Full JSON aggregate must be an object with a 'type' key.")

    return agg_obj


def parse_aggregate_string(s):
    """
    Parses a transformation-style aggregator string into a structured aggregator.

    Expected format:
         "agg_type:range1,range2,..."
    where each range is in the format "<key>_<from>-<to>".

    If the string does not contain a colon, it is returned as-is.

    :param s: Aggregator string.
    :type s: str
    :return: Aggregator object (dict) if colon is present, else the original string.
    """
    if ":" not in s:
        return s

    try:
        agg_type, range_str = s.split(":", 1)
    except ValueError:
        raise ValueError("Aggregator string must contain a colon separating type and ranges.")

    agg_type = agg_type.strip()
    ranges = []

    for part in range_str.split(","):
        part = part.strip()
        if not part:
            continue

        range_dict = parse_range_definition(part)
        ranges.append(range_dict)

    result = {"type": agg_type, "ranges": ranges}
    return result


def parse_range_definition(part):
    """
    Parses a single range definition in the format "<key>_<range_value>".

    :param part: Range definition string.
    :type part: str
    :return: Dict with 'key' and parsed 'from' and/or 'to' values.
    """
    if "_" not in part:
        raise ValueError("Range definition '{}' must contain an underscore separating key and value.".format(part))

    key, value = part.split("_", 1)
    key = key.strip()
    value = value.strip()

    if "-" not in value:
        raise ValueError("Range value in '{}' must contain a dash (-) separating from and to values.".format(part))

    from_val, to_val = parse_range_bounds(value, part)
    range_dict = {"key": key}

    if from_val is not None:
        range_dict["from"] = from_val

    if to_val is not None:
        range_dict["to"] = to_val

    return range_dict


def parse_range_bounds(value, part):
    """
    Parses a range value in the format "from-to", where either may be omitted.
    Returns numeric values (int if whole number, else float) or None.

    :param value: Range value string.
    :type value: str
    :param part: Original range definition string.
    :type part: str
    :return: Tuple (from_val, to_val) as numbers or None.
    """
    parts = value.split("-", 1)
    from_val = parse_numeric_value(parts[0], "from", part)
    to_val = parse_numeric_value(parts[1], "to", part)

    return from_val, to_val

def parse_numeric_value(value, label, part):
    """
    Parses a numeric value (int or float) or returns None if the value is empty.

    :param value: The string to parse.
    :type value: str
    :param label: The label ('from' or 'to') for error messages.
    :type label: str
    :param part: The original range definition string for error context.
    :type part: str
    :return: Parsed numeric value (int or float) or None.
    :rtype: int, float, or None
    :raises ValueError: If the value is not a valid number.
    """
    value = value.strip() if value else value
    try:
        num = float(value) if value else None
        return int(num) if num is not None and num.is_integer() else num
    except ValueError:
        raise ValueError(f"Invalid numeric value for '{label}' in range '{part}'.")
