from notifier.trading_alerts import (
    format_near_miss,
    format_open,
    format_pick,
    format_rejected,
    format_score_detail,
)


def test_format_pick_with_score_detail():
    msg = format_pick("TRBUSDT", "long", 85.0, detail="struct=30 vol=25(1.2x)")
    assert "🎯 PICK TRBUSDT LONG" in msg
    assert "score=85" in msg
    assert "struct=30" in msg


def test_format_rejected():
    assert "REJECTED TRBUSDT risk_blocked" in format_rejected("TRBUSDT", "risk_blocked")


def test_format_near_miss():
    msg = format_near_miss("DOGEUSDT", 82.0)
    assert "Near-miss DOGEUSDT" in msg
    assert "score=82" in msg


def test_format_open_includes_levels():
    msg = format_open(
        "TRBUSDT",
        "long",
        100.0,
        16.86,
        16.50,
        17.58,
        tp_r=2.0,
    )
    assert "OPEN TRBUSDT LONG" in msg
    assert "SL 16.5000" in msg
    assert "TP 17.5800" in msg
    assert "2R" in msg


def test_format_score_detail_empty():
    assert format_score_detail(None) == ""
    assert format_score_detail({}) == ""
