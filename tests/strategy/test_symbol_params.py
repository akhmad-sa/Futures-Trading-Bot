from strategy.symbol_params import resolve_strategy_params


def test_btc_has_strict_baseline():
    params = resolve_strategy_params("trendline_breakout", "BTCUSDT")
    assert params["min_signal_score"] == 70
    assert params["require_confirmed_structure"] is True
    assert params["allow_pending_structure"] is False


def test_eth_stricter_than_btc():
    btc = resolve_strategy_params("trendline_breakout", "BTCUSDT")
    eth = resolve_strategy_params("trendline_breakout", "ETHUSDT")
    assert eth["min_signal_score"] >= btc["min_signal_score"]
    assert eth["vol_multiplier"] >= btc["vol_multiplier"]


def test_env_min_signal_score_overrides_and_relaxes_structure():
    class Cfg:
        min_signal_score = 50.0
        symbol_strategy_params = {}
        model_fields_set = {"min_signal_score"}

    params = resolve_strategy_params("trendline_breakout", "ETHUSDT", config=Cfg())
    assert params["min_signal_score"] == 50
    assert params["require_confirmed_structure"] is False


def test_min_signal_score_82_from_config():
    class Cfg:
        min_signal_score = 82.0
        symbol_strategy_params = {}
        model_fields_set = {"min_signal_score"}

    params = resolve_strategy_params("trendline_breakout", "XRPUSDT", config=Cfg())
    assert params["min_signal_score"] == 82
