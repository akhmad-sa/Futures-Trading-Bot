"""Tests for structure event logging (file log, not stdout)."""

from datetime import datetime, timezone

from market_structure.event_log import StructureEventLogger
from market_structure.bos_choch import StructureState
from market_structure.swing_structure import TrendStructure


def _state(**kwargs) -> StructureState:
    return StructureState(
        trend=kwargs.get("trend", TrendStructure.NEUTRAL),
        bias=kwargs.get("bias", TrendStructure.NEUTRAL),
        last_break=None,
    )


def test_events_mode_logs_only_on_state_change(caplog):
    logger = StructureEventLogger(mode="events", structure_timeframe="1h")
    ts = datetime(2026, 5, 21, 0, 20, tzinfo=timezone.utc)
    state = _state(
        trend=TrendStructure.UPTREND,
        bias=TrendStructure.UPTREND,
    )

    with caplog.at_level("INFO"):
        logger.record_scan("BTCUSDT", state, ts)
        logger.record_scan("BTCUSDT", state, ts)
        logger.record_scan("BTCUSDT", state, ts)

    structure_lines = [r for r in caplog.records if "[STRUCTURE]" in r.message]
    assert len(structure_lines) == 1
    assert "INIT" in structure_lines[0].message


def test_events_mode_logs_skip_reason_once(caplog):
    logger = StructureEventLogger(mode="events", structure_timeframe="1h")
    ts = datetime(2026, 5, 21, 10, 55, tzinfo=timezone.utc)
    state = _state()

    with caplog.at_level("INFO"):
        logger.record_scan("BTCUSDT", state, ts, hold_reason="counter_choch")
        logger.record_scan("BTCUSDT", state, ts, hold_reason="counter_choch")

    skip_lines = [r for r in caplog.records if "skip=counter_choch" in r.message]
    assert len(skip_lines) == 1


def test_off_mode_silent(caplog):
    logger = StructureEventLogger(mode="off")
    ts = datetime(2026, 5, 21, 0, 0, tzinfo=timezone.utc)
    with caplog.at_level("INFO"):
        logger.record_scan("BTCUSDT", _state(), ts)
    assert not [r for r in caplog.records if "[STRUCTURE]" in r.message]


def test_full_mode_logs_every_scan(caplog):
    logger = StructureEventLogger(mode="full", structure_timeframe="1h")
    ts = datetime(2026, 5, 21, 0, 0, tzinfo=timezone.utc)
    state = _state()
    with caplog.at_level("INFO"):
        logger.record_scan("BTCUSDT", state, ts)
        logger.record_scan("BTCUSDT", state, ts)
    structure_lines = [r for r in caplog.records if "[STRUCTURE]" in r.message]
    assert len(structure_lines) == 2
