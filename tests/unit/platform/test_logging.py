"""Unit tests for Centralized Structured Logging and Context Propagation."""
import json
import logging
from app.domains.platform.logging import (
    LogBuffer,
    StructuredLogEntry,
    StructuredLogger,
    get_structured_logger,
    log_context,
)


def test_structured_log_entry_creation():
    entry = StructuredLogEntry(
        level="INFO",
        logger="test.logger",
        message="Test message",
        correlation_id="corr-123",
        symbol="RELIANCE",
    )
    assert entry.level == "INFO"
    assert entry.logger == "test.logger"
    assert entry.correlation_id == "corr-123"
    assert entry.symbol == "RELIANCE"
    json_str = entry.model_dump_json()
    data = json.loads(json_str)
    assert data["message"] == "Test message"
    assert data["correlation_id"] == "corr-123"


def test_log_context_propagation():
    logger = get_structured_logger("test.context")
    buffer = LogBuffer(capacity=10)

    with log_context(
        correlation_id="corr-999",
        cycle_id="cycle-888",
        strategy_id="strat-alpha",
        stage="strategy_eval",
    ):
        entry = logger._build_entry("INFO", "Evaluating alpha signal")
        assert entry.correlation_id == "corr-999"
        assert entry.cycle_id == "cycle-888"
        assert entry.strategy_id == "strat-alpha"
        assert entry.stage == "strategy_eval"

    # Outside context, contextvars reset
    outside_entry = logger._build_entry("INFO", "Outside context")
    assert outside_entry.correlation_id is None
    assert outside_entry.cycle_id is None


def test_log_buffer_circular_and_query():
    buffer = LogBuffer(capacity=3)
    e1 = StructuredLogEntry(level="INFO", logger="test", message="m1", correlation_id="c1")
    e2 = StructuredLogEntry(level="WARNING", logger="test", message="m2", correlation_id="c1")
    e3 = StructuredLogEntry(level="ERROR", logger="test", message="m3", correlation_id="c2")
    e4 = StructuredLogEntry(level="INFO", logger="test", message="m4", correlation_id="c1")

    buffer.append(e1)
    buffer.append(e2)
    buffer.append(e3)
    assert buffer.size == 3

    # Adding 4th drops 1st (capacity=3)
    buffer.append(e4)
    assert buffer.size == 3

    all_entries = buffer.get_entries()
    assert len(all_entries) == 3
    assert all_entries[0].message == "m4"  # Reversed (most recent first)

    filtered_c1 = buffer.get_entries(correlation_id="c1")
    assert len(filtered_c1) == 2

    filtered_err = buffer.get_entries(level="ERROR")
    assert len(filtered_err) == 1
    assert filtered_err[0].message == "m3"


def test_logger_bound_context():
    logger = get_structured_logger("base.logger")
    bound = logger.bind(portfolio_id="port-101", user_id="user-202")

    entry = bound._build_entry("DEBUG", "Bound test")
    assert entry.extra.get("portfolio_id") == "port-101"
    assert entry.extra.get("user_id") == "user-202"
