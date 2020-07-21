import unittest

from cloudinary_cli.utils.utils import parse_option_value, only_fields, merge_responses


class UtilsTest(unittest.TestCase):
    def test_parse_option_value(self):
        """ should parse option values correctly """
        self.assertEqual("haha,123,1234", parse_option_value("haha,123,1234"))
        self.assertTrue(parse_option_value("True"))
        self.assertFalse(parse_option_value("false"))
        self.assertListEqual(["test", "123"], parse_option_value('["test","123"]'))
        self.assertDictEqual({"foo": "bar"}, parse_option_value('{"foo":"bar"}'))
        self.assertDictEqual({"an": "object", "or": "dict"}, parse_option_value('{"an":"object","or":"dict"}'))
        self.assertListEqual(["this", "will", "be", "read", "as",
                              "a", "list"], parse_option_value('["this","will","be","read","as","a","list"]'))

    def test_parse_option_value_converts_int_to_str(self):
        """ should convert a parsed int to a str """
        self.assertEqual("1", parse_option_value(1))

    def test_only_fields(self):
        """ should filter fields correctly """
        self.assertEqual([{"1": "2"}], only_fields([{"1": "2", "3": "4"}], "1"))

    def test_merge_responses(self):
        """ should merge responses based with or without additional kwargs """

        merged_1 = ({"a": "b", "c": [{"1": "2"}, {"1": "3"}, {"1": "4"}, {"1": "5"}]}, "c")
        merged_1_2 = (
            {"a": "b", "c": [{"1": "2", "2": "2"}, {"1": "3", "2": "2"}, {"1": "4", "2": "2"}, {"1": "5", "2": "2"}]},
            "c"
        )
        self.assertEqual(
            merged_1,
            merge_responses(
                {"a": "b", "c": [{"1": "2", "2": "2"}, {"1": "3", "2": "2"}]},
                {"a": "b", "c": [{"1": "4", "2": "2"}, {"1": "5", "2": "2"}]},
                fields_to_keep=["1"]))
        self.assertEqual(
            merged_1,
            merge_responses(
                {"a": "b", "c": [{"1": "2"}, {"1": "3"}]},
                {"a": "b", "c": [{"1": "4", "2": "2"}, {"1": "5", "2": "2"}]},
                fields_to_keep=["1"],
                paginate_field="c"))
        self.assertEqual(
            merged_1_2,
            merge_responses(
                {"a": "b", "c": [{"1": "2", "2": "2"}, {"1": "3", "2": "2"}]},
                {"a": "b", "c": [{"1": "4", "2": "2"}, {"1": "5", "2": "2"}]},
                paginate_field="c"))
        self.assertEqual(
            merged_1_2,
            merge_responses(
                {"a": "b", "c": [{"1": "2", "2": "2"}, {"1": "3", "2": "2"}]},
                {"a": "b", "c": [{"1": "4", "2": "2"}, {"1": "5", "2": "2"}]}))
