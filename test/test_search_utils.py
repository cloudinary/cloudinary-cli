import unittest
from cloudinary_cli.utils.search_utils import (
    parse_aggregate,
    parse_json_aggregate,
    parse_aggregate_string,
    parse_range_definition,
    parse_range_bounds
)


class TestAggregateParsing(unittest.TestCase):

    # --- Tests for parse_json_aggregate ---

    def test_parse_json_aggregate_valid(self):
        s = '{"type": "bytes", "ranges": [{"key": "tiny", "to": 500}]}'
        result = parse_json_aggregate(s)
        expected = {"type": "bytes", "ranges": [{"key": "tiny", "to": 500}]}
        self.assertEqual(expected, result)

    def test_parse_json_aggregate_invalid_json(self):
        s = '{"type": "bytes", "ranges": [{"key": "tiny", "to": 500}'  # missing closing ]
        with self.assertRaises(ValueError):
            parse_json_aggregate(s)

    def test_parse_json_aggregate_missing_type(self):
        s = '{"ranges": [{"key": "tiny", "to": 500}]}'
        with self.assertRaises(ValueError):
            parse_json_aggregate(s)

    # --- Tests for parse_aggregate_string ---

    def test_parse_aggregate_string_valid(self):
        s = "bytes:tiny_-500,medium_501-1999,big_2000-"
        result = parse_aggregate_string(s)
        expected = {
            "type": "bytes",
            "ranges": [
                {"key": "tiny", "to": 500},
                {"key": "medium", "from": 501, "to": 1999},
                {"key": "big", "from": 2000}
            ]
        }
        self.assertEqual(expected, result)

    def test_parse_aggregate_string_no_colon(self):
        s = "format"
        result = parse_aggregate_string(s)
        self.assertEqual(s, result)

    # --- Tests for parse_aggregate (supports list and non-string inputs) ---

    def test_parse_aggregate_simple_string(self):
        s = "format"
        result = parse_aggregate(s)
        self.assertEqual([s], result)

    def test_parse_aggregate_json(self):
        s = '{"type": "bytes", "ranges": [{"key": "tiny", "to": 500}]}'
        result = parse_aggregate(s)
        expected = [{"type": "bytes", "ranges": [{"key": "tiny", "to": 500}]}]
        self.assertEqual(expected, result)

    def test_parse_aggregate_transformation_string(self):
        s = "bytes:tiny_-500,medium_501-1999,big_2000-"
        result = parse_aggregate(s)
        expected = [{
            "type": "bytes",
            "ranges": [
                {"key": "tiny", "to": 500},
                {"key": "medium", "from": 501, "to": 1999},
                {"key": "big", "from": 2000}
            ]
        }]
        self.assertEqual(expected, result)

    def test_parse_aggregate_list_input(self):
        input_list = [
            "format",
            "bytes:tiny_-500,medium_501-1999,big_2000-"
        ]
        result = parse_aggregate(input_list)
        expected = [
            "format",
            {
                "type": "bytes",
                "ranges": [
                    {"key": "tiny", "to": 500},
                    {"key": "medium", "from": 501, "to": 1999},
                    {"key": "big", "from": 2000}
                ]
            }
        ]
        self.assertEqual(expected, result)

    def test_parse_aggregate_non_string(self):
        # If a non-string (e.g. dict) is passed, build_array wraps it, and it is returned as is.
        d = {"type": "custom", "value": 123}
        result = parse_aggregate(d)
        self.assertEqual([d], result)

    # --- Tests for parse_range_definition ---

    def test_parse_range_definition_valid_tiny(self):
        part = "tiny_-500"
        result = parse_range_definition(part)
        expected = {"key": "tiny", "to": 500}
        self.assertEqual(expected, result)

    def test_parse_range_definition_valid_medium(self):
        part = "medium_501-1999"
        result = parse_range_definition(part)
        expected = {"key": "medium", "from": 501, "to": 1999}
        self.assertEqual(expected, result)

    def test_parse_range_definition_valid_big(self):
        part = "big_2000-"
        result = parse_range_definition(part)
        expected = {"key": "big", "from": 2000}
        self.assertEqual(expected, result)

    def test_parse_range_definition_missing_underscore(self):
        part = "big2000-"
        with self.assertRaises(ValueError):
            parse_range_definition(part)

    def test_parse_range_definition_missing_dash(self):
        part = "big_2000"
        with self.assertRaises(ValueError):
            parse_range_definition(part)

    # --- Tests for parse_range_bounds ---

    def test_parse_range_bounds_whole_numbers(self):
        value = "501-1999"
        result = parse_range_bounds(value, "test")
        expected = (501, 1999)
        self.assertEqual(expected, result)

    def test_parse_range_bounds_floats(self):
        value = "24.5-29.97"
        result = parse_range_bounds(value, "test")
        expected = (24.5, 29.97)
        self.assertEqual(expected, result)

    def test_parse_range_bounds_empty_from(self):
        value = "-500"
        result = parse_range_bounds(value, "test")
        expected = (None, 500)
        self.assertEqual(expected, result)

    def test_parse_range_bounds_empty_to(self):
        value = "2000-"
        result = parse_range_bounds(value, "test")
        expected = (2000, None)
        self.assertEqual(expected, result)

    def test_parse_range_bounds_invalid_from(self):
        value = "abc-100"
        with self.assertRaises(ValueError):
            parse_range_bounds(value, "test")

    def test_parse_range_bounds_invalid_to(self):
        value = "100-abc"
        with self.assertRaises(ValueError):
            parse_range_bounds(value, "test")


if __name__ == '__main__':
    unittest.main()
