import unittest

from cloudinary_cli.utils.utils import parse_option_value, parse_args_kwargs, whitelist_keys, merge_responses, \
    normalize_list_params


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
        """ should convert a parsed 0 to a str """
        self.assertEqual("0", parse_option_value(0))
        self.assertEqual(1, parse_option_value(1))

    def test_parse_args_kwargs(self):
        args, kwargs = parse_args_kwargs(_no_args_test_func, [])
        self.assertEqual(0, len(args))
        self.assertEqual(0, len(kwargs))

        args, kwargs = parse_args_kwargs(_only_args_test_func, ["a1", "a2"])
        self.assertListEqual(["a1", "a2"], args)
        self.assertEqual(0, len(kwargs))

        with self.assertRaisesRegex(Exception, "requires 2 arguments"):
            parse_args_kwargs(_only_args_test_func, ["a1"])

        args, kwargs = parse_args_kwargs(_args_kwargs_test_func, ["a1", 'arg2=a2'])
        self.assertListEqual(["a1"], args)
        self.assertDictEqual({"arg2": "a2"}, kwargs)

        # should parse values
        args, kwargs = parse_args_kwargs(_args_kwargs_test_func, ['["a1"]', 'arg2={"k2":"a2"}'])
        self.assertListEqual([["a1"]], args)
        self.assertDictEqual({"arg2": {"k2": "a2"}}, kwargs)

        # should allow passing optional args as positional
        args, kwargs = parse_args_kwargs(_args_kwargs_test_func, ["a1", "a2"])
        self.assertListEqual(["a1", "a2"], args)
        self.assertEqual(0, len(kwargs))

    def test_whitelist_keys(self):
        """ should whitelist keys correctly """
        self.assertEqual([{"k1": "v1"}], whitelist_keys([{"k1": "v1", "k2": "v2"}], ["k1"]))
        self.assertEqual([{"k1": "v1", "k2": "v2"}], whitelist_keys([{"k1": "v1", "k2": "v2"}], []))
        self.assertEqual([{"k1": "v1"}], whitelist_keys([{"k1": "v1", "k2": "v2"}], ["k1", "k3"]))

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
                pagination_field="c"))
        self.assertEqual(
            merged_1_2,
            merge_responses(
                {"a": "b", "c": [{"1": "2", "2": "2"}, {"1": "3", "2": "2"}]},
                {"a": "b", "c": [{"1": "4", "2": "2"}, {"1": "5", "2": "2"}]},
                pagination_field="c"))
        self.assertEqual(
            merged_1_2,
            merge_responses(
                {"a": "b", "c": [{"1": "2", "2": "2"}, {"1": "3", "2": "2"}]},
                {"a": "b", "c": [{"1": "4", "2": "2"}, {"1": "5", "2": "2"}]}))

    def test_normalize_list_params(self):
        """ should normalize a list of parameters """
        self.assertEqual(["f1", "f2", "f3"], normalize_list_params(["f1,f2", "f3"]))


def _no_args_test_func():
    pass


def _only_args_test_func(arg1, arg2):
    return arg1, arg2


def _args_kwargs_test_func(arg1, arg2=None):
    return arg1, arg2
