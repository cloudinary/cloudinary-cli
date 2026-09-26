import builtins
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from cloudinary_cli.utils.utils import parse_option_value, parse_args_kwargs, whitelist_keys, merge_responses, \
    normalize_list_params, chunker, group_params, confirm_action, get_user_action, prompt_user, is_interactive, \
    parse_expiry, is_expired, expires_in_hint, write_json_list_to_csv


NOW = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)


class ExpiryHelpersTest(unittest.TestCase):
    """Generic expiry helpers, shared by the OAuth token expiry (epoch) and the Claimable Cloud
    expiry (ISO-8601 string)."""

    EPOCH = int(NOW.timestamp())

    def test_parses_iso_with_z_offset_and_naive_alike(self):
        for value in ("2026-08-19T12:00:00Z", "2026-08-19T12:00:00+00:00", "2026-08-19T12:00:00"):
            self.assertEqual(NOW, parse_expiry(value), value)

    def test_parses_epoch_as_int_and_string(self):
        self.assertEqual(NOW, parse_expiry(self.EPOCH))
        self.assertEqual(NOW, parse_expiry(str(self.EPOCH)))

    def test_non_utc_offset_is_honoured(self):
        self.assertEqual(NOW, parse_expiry("2026-08-19T14:00:00+02:00"))

    def test_unreadable_values_parse_to_none(self):
        for value in (None, "", "not-a-date", True, [], {}):
            self.assertIsNone(parse_expiry(value), repr(value))

    def test_is_expired_distinguishes_unknown_from_expired(self):
        self.assertTrue(is_expired("2020-01-01T00:00:00Z", now=NOW))
        self.assertFalse(is_expired("2027-01-01T00:00:00Z", now=NOW))
        self.assertIsNone(is_expired("not-a-date"))  # unknown, not expired

    def test_countdown_rounds_rather_than_truncates(self):
        # 7h59m reads as 8h, not 7h
        self.assertEqual("expires in 8h", expires_in_hint(NOW + timedelta(hours=7, minutes=59), now=NOW))

    def test_countdown_units(self):
        self.assertEqual("expires in 45m", expires_in_hint(NOW + timedelta(minutes=45), now=NOW))
        self.assertEqual("expires in 24h", expires_in_hint(NOW + timedelta(hours=24), now=NOW))
        self.assertEqual("expires in 3d", expires_in_hint(NOW + timedelta(days=3), now=NOW))

    def test_countdown_never_reads_zero_minutes(self):
        self.assertEqual("expires in 1m", expires_in_hint(NOW + timedelta(seconds=20), now=NOW))

    def test_countdown_labels_are_overridable(self):
        self.assertEqual("expired", expires_in_hint(NOW - timedelta(seconds=1), now=NOW))
        self.assertEqual("gone", expires_in_hint(NOW - timedelta(seconds=1), now=NOW, expired_label="gone"))
        self.assertEqual("", expires_in_hint("not-a-date"))
        self.assertEqual("unknown", expires_in_hint("not-a-date", unknown_label="unknown"))

    def test_accepts_a_datetime_directly(self):
        self.assertEqual("expires in 2h", expires_in_hint(NOW + timedelta(hours=2), now=NOW))


class NonInteractiveInputTest(unittest.TestCase):
    """A confirmation/selection prompt on closed (non-interactive) stdin must apply the default and
    surface a hint, not raise EOFError up to a blank 'Command execution failed' with exit 0."""

    def _eof(self, *args):
        raise EOFError("EOF when reading a line")

    def test_confirm_action_defaults_to_no_on_eof(self):
        with patch.object(builtins, "input", self._eof), \
                patch("cloudinary_cli.utils.utils.logger.warning") as warn:
            self.assertFalse(confirm_action())
        warn.assert_called_once()
        self.assertIn("--force", warn.call_args[0][0])

    def test_get_user_action_returns_default_on_eof(self):
        with patch.object(builtins, "input", self._eof):
            self.assertEqual("fallback",
                             get_user_action("pick: ", {"y": True, "default": "fallback"}))

    def test_get_user_action_no_hint_when_not_provided(self):
        with patch.object(builtins, "input", self._eof), \
                patch("cloudinary_cli.utils.utils.logger.warning") as warn:
            self.assertIsNone(get_user_action("pick: ", {"y": True}))
        warn.assert_not_called()

    def test_empty_line_still_uses_default(self):
        # An empty line (piped) is distinct from EOF and already used the default; keep that intact.
        with patch.object(builtins, "input", lambda *a: ""):
            self.assertFalse(confirm_action())

    def test_prompt_user_returns_line_when_available(self):
        with patch.object(builtins, "input", lambda *a: "  2 "):
            self.assertEqual("  2 ", prompt_user("pick: "))

    def test_prompt_user_returns_none_and_hints_on_eof(self):
        with patch.object(builtins, "input", self._eof), \
                patch("cloudinary_cli.utils.utils.logger.warning") as warn:
            self.assertIsNone(prompt_user("pick: ", noninteractive_hint="do X instead"))
        warn.assert_called_once()
        self.assertIn("do X instead", warn.call_args[0][0])

    def test_is_interactive_reflects_stdin_isatty(self):
        with patch("cloudinary_cli.utils.utils.sys.stdin.isatty", return_value=True):
            self.assertTrue(is_interactive())
        with patch("cloudinary_cli.utils.utils.sys.stdin.isatty", return_value=False):
            self.assertFalse(is_interactive())


class UtilsTest(unittest.TestCase):
    def test_parse_option_value(self):
        """ should parse option values correctly """
        self.assertEqual("haha,123,1234", parse_option_value("haha,123,1234"))
        self.assertTrue(parse_option_value("True"))
        self.assertFalse(parse_option_value("false"))
        self.assertListEqual(["test", "123"], parse_option_value('["test","123"]'))
        self.assertDictEqual({"foo": "bar"}, parse_option_value('{"foo":"bar"}'))
        self.assertDictEqual({"an": "object", "or": "dict"}, parse_option_value('{"an":"object","or":"dict"}'))
        self.assertListEqual(
            ["this", "will", "be", "read", "as", "a", "list"],
            parse_option_value('["this","will","be","read","as","a","list"]')
        )
        self.assertListEqual(
            [True, False, 123, '0', ['test', '123']],
            parse_option_value(["True", "false", "123", "0", '["test","123"]'])
        )

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

        with self.assertRaisesRegex(Exception, "requires 2 positional arguments"):
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

        # should allow passing positional as optional
        args, kwargs = parse_args_kwargs(_only_args_test_func, ["a1"], {"arg2": "a2"})
        self.assertListEqual(["a1"], args)
        self.assertDictEqual({"arg2": "a2"}, kwargs)

        args, kwargs = parse_args_kwargs(_only_args_test_func, [], {"arg1": "a1", "arg2": "a2"})
        self.assertEqual(0, len(args))
        self.assertDictEqual({"arg1": "a1", "arg2": "a2"}, kwargs)

        # should consume list values separated by spaces and commas
        args, kwargs = parse_args_kwargs(_list_args_test_func, ["l0a0,l0a1,l0a2", "sa0", "l1a0", "sa2", "l1a1,l1a2", "l1a3"])
        self.assertEqual(4, len(args))
        self.assertListEqual(["l0a0", "l0a1", "l0a2"], args[0])
        self.assertEqual("sa0", args[1])
        self.assertListEqual(["l1a0", "l1a1", "l1a2", "l1a3"], args[2])
        self.assertEqual("sa2", args[3])

        # should consume list values separated by spaces and commas in kwargs
        args, kwargs = parse_args_kwargs(_list_args_test_func,
                                         ["l0a0,l0a1,l0a2", "sa0"], {"list_arg": "l1a0,l1a1", "non_list_arg2": "sa2"})
        self.assertEqual(2, len(args))
        self.assertListEqual(["l0a0", "l0a1", "l0a2"], args[0])
        self.assertEqual("sa0", args[1])
        self.assertListEqual(["l1a0", "l1a1"], kwargs["list_arg"])
        self.assertEqual("sa2", kwargs["non_list_arg2"])

    def test_group_params(self):
        self.assertDictEqual({}, group_params([]))
        self.assertDictEqual({"k1": "v1", "k2": "v2"}, group_params([("k1", "v1"), ("k2", "v2")]))
        self.assertDictEqual({"k1": ["v1", "v2"]}, group_params([("k1", "v1"), ("k1", "v2")]))
        self.assertDictEqual({"k1": "v1", "k2": ["v2", "v3"]}, group_params([("k1", "v1"), ("k2", "v2"), ("k2", "v3")]))
        self.assertDictEqual(
            {"k1": ["v1", "v2", "v3"]},
            group_params([("k1", "v1")], [("k1", "v2")], [("k1", "v3")])
        )

    def test_write_json_list_to_csv_file_name(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            for name, expected in (("out", "out.csv"), ("out.csv", "out.csv"), ("out.CSV", "out.CSV")):
                filename = write_json_list_to_csv([{"k1": "v1"}], os.path.join(tmp_dir, name))

                self.assertEqual(os.path.join(tmp_dir, expected), filename)
                self.assertTrue(os.path.isfile(filename))

            self.assertEqual(["out.CSV", "out.csv"], sorted(os.listdir(tmp_dir)))

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
        self.assertListEqual(["f1"], normalize_list_params("f1"))
        self.assertListEqual(["f1", "f2", "f3"], normalize_list_params(["f1,f2", "f3"]))
        self.assertListEqual(["f1", "f2", "f3"], normalize_list_params("f1,f2,f3"))

    def test_chunker(self):
        animals = ['cat', 'dog', 'rabbit', 'duck', 'bird', 'cow', 'gnu', 'fish']
        groups = [group for group in chunker(animals, 3)]
        self.assertListEqual([['cat', 'dog', 'rabbit'], ['duck', 'bird', 'cow'], ['gnu', 'fish']], groups)


def _no_args_test_func():
    pass


def _only_args_test_func(arg1, arg2):
    return arg1, arg2


def _args_kwargs_test_func(arg1, arg2=None):
    return arg1, arg2


def _list_args_test_func(fist_list_arg, non_list_arg, list_arg=None, non_list_arg2=None):
    """
    Function for testing list args.

    :param fist_list_arg: first list argument
    :type fist_list_arg: list
    :param non_list_arg: some non-list argument
    :type non_list_arg: str
    :param list_arg: some list argument
    :type list_arg: list
    :param non_list_arg2: another non-list argument
    :type non_list_arg2: str
    :return: tuple of arguments
    :rtype: tuple
    """
    return fist_list_arg, non_list_arg, list_arg, non_list_arg2
