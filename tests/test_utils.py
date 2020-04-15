import unittest

from cloudinary_cli.utils.utils import parse_option_value


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
