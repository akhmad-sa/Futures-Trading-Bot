from risk.exit_levels import (
    PositionExitState,
    apply_stepped_trailing_sl,
    lock_r_for_milestone,
)


def test_lock_r_for_milestone():
    assert lock_r_for_milestone(1, 2) == 0.0
    assert lock_r_for_milestone(2, 2) == 0.0
    assert lock_r_for_milestone(3, 2) == 1.0
    assert lock_r_for_milestone(4, 2) == 2.0
    assert lock_r_for_milestone(5, 2) == 3.0


def test_stepped_trail_long_ratchet():
    state = PositionExitState(
        side="long",
        entry_price=100.0,
        stop_loss=98.0,
        take_profit=200.0,
        initial_risk=2.0,
    )
    state, events = apply_stepped_trailing_sl(
        state, 106.0, enabled=True, lock_offset=2.0
    )
    assert state.stop_loss == 102.0
    assert state.trail_milestone_r == 3.0
    assert len(events) == 2
    assert state.reached_1r is True


def test_stepped_trail_short_ratchet():
    state = PositionExitState(
        side="short",
        entry_price=100.0,
        stop_loss=102.0,
        take_profit=0.0,
        initial_risk=2.0,
    )
    state, events = apply_stepped_trailing_sl(
        state, 94.0, enabled=True, lock_offset=2.0
    )
    assert state.stop_loss == 98.0
    assert state.trail_milestone_r == 3.0


def test_stepped_trail_does_not_loosen():
    state = PositionExitState(
        side="long",
        entry_price=100.0,
        stop_loss=102.0,
        take_profit=200.0,
        initial_risk=2.0,
        trail_milestone_r=3.0,
    )
    state, events = apply_stepped_trailing_sl(
        state, 101.0, enabled=True, lock_offset=2.0
    )
    assert state.stop_loss == 102.0
    assert events == []
