from notifier.control import normalize_chat_id, parse_command


def test_normalize_chat_id_from_int():
    assert normalize_chat_id(-1001234567890) == "-1001234567890"
    assert normalize_chat_id(12345) == "12345"


def test_parse_command():
    assert parse_command("/test@MyBot")[0] == "/test"
