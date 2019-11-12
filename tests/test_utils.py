from cloudinary_cli.utils import parse_option_value


def test_parse_option_value():
    """ should parse option values correctly """
    assert parse_option_value("haha,123,1234") == "haha,123,1234"
    assert parse_option_value("True") == True
    assert parse_option_value("false") == False
    assert parse_option_value('["test","123"]') == ['test', '123']
    assert parse_option_value('{"foo":"bar"}') == {"foo":"bar"}
    assert parse_option_value('{"an":"object","or":"dict"}') == {"an": "object", "or": "dict"}
    assert parse_option_value('["this","will","be","read","as","a","list"]') == \
           ["this", "will", "be", "read", "as", "a", "list"]

def test_parse_option_value_converts_int_to_str():
    """ should convert a parsed int to a str """
    assert parse_option_value(1) == "1"
