from risk.exit_levels import (
    PositionExitState,
    has_reached_r,
    should_take_partial_profit,
    update_milestones,
)


def _state(side: str = "long", entry: float = 100.0, risk: float = 2.0) -> PositionExitState:
    sl = entry - risk if side == "long" else entry + risk
    tp = entry + risk if side == "long" else entry - risk
    return PositionExitState(
        side=side,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        initial_risk=risk,
    )


def test_reached_1r_long():
    state = _state("long")
    assert not has_reached_r(state, 101.0, 1.0)
    assert has_reached_r(state, 102.0, 1.0)


def test_update_milestones_sets_reached_1r_and_breakeven():
    state = _state("long")
    updated, events = update_milestones(
        state, 102.0, breakeven_enabled=True, stepped_trail_enabled=False
    )
    assert updated.reached_1r is True
    assert updated.stop_loss >= state.entry_price
    assert events == []


def test_partial_profit_once_at_1r():
    state = _state("short", entry=100.0, risk=1.0)
    assert should_take_partial_profit(
        state, 99.0, enabled=True, at_r=1.0, pct=50.0
    )
    state.partial_profit_taken = True
    assert not should_take_partial_profit(
        state, 99.0, enabled=True, at_r=1.0, pct=50.0
    )


def test_trend_exit_blocked_before_1r():
    from risk.manager import RiskManager

    class Cfg:
        use_trend_exit = True
        trend_exit_after_1r_only = True

    rm = RiskManager(Cfg())
    state = PositionExitState(
        side="long",
        entry_price=100.0,
        stop_loss=98.0,
        take_profit=300.0,
        initial_risk=2.0,
    )
    assert rm.is_trend_exit_allowed(state) is False
    state.reached_1r = True
    assert rm.is_trend_exit_allowed(state) is True
