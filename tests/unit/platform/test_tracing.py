"""Unit tests for Distributed Tracing and Span Management."""
import time
import uuid
from app.domains.platform.tracing import (
    SpanKind,
    SpanStatus,
    TraceCollector,
    trace_span,
    traced,
)


def test_trace_span_hierarchical_creation():
    collector = TraceCollector(capacity=10)
    root_trace_id = uuid.uuid4()

    with trace_span("root_operation", trace_id=root_trace_id, collector=collector) as root:
        root.set_tag("env", "test")
        root.log_event("sub_event_1", {"key": "val"})

        with trace_span("child_operation_1", collector=collector) as child1:
            child1.set_tag("child_id", 1)
            time.sleep(0.005)

        with trace_span("child_operation_2", collector=collector) as child2:
            child2.set_tag("child_id", 2)

    traces = collector.get_traces()
    assert len(traces) == 1
    tr = traces[0]
    assert tr.trace_id == root_trace_id
    assert tr.name == "root_operation"
    assert tr.status == SpanStatus.ok
    assert tr.duration_ms is not None and tr.duration_ms > 0
    assert len(tr.spans) == 3

    # Check child relationships
    root_span = next(s for s in tr.spans if s.name == "root_operation")
    child_spans = [s for s in tr.spans if s.name != "root_operation"]
    assert len(child_spans) == 2
    for cs in child_spans:
        assert cs.parent_id == root_span.span_id
        assert cs.trace_id == root_trace_id


def test_trace_span_error_handling():
    collector = TraceCollector(capacity=10)

    try:
        with trace_span("failing_stage", collector=collector):
            raise ValueError("Simulated pipeline failure")
    except ValueError:
        pass

    traces = collector.get_traces()
    assert len(traces) == 1
    tr = traces[0]
    assert tr.status == SpanStatus.error
    assert len(tr.spans) == 1
    assert "Simulated pipeline failure" in (tr.spans[0].error_message or "")


def test_traced_decorator():
    collector = TraceCollector(capacity=10)

    @traced(name="decorated_service_call", kind=SpanKind.internal)
    def my_service(x: int) -> int:
        return x * 2

    res = my_service(21)
    assert res == 42


def test_trace_collector_filtering():
    collector = TraceCollector(capacity=10)
    t1_id = uuid.uuid4()
    t2_id = uuid.uuid4()

    with trace_span("op_alpha", trace_id=t1_id, collector=collector):
        pass

    with trace_span("op_beta", trace_id=t2_id, collector=collector):
        pass

    alpha_traces = collector.get_traces(name="alpha")
    assert len(alpha_traces) == 1
    assert alpha_traces[0].name == "op_alpha"

    by_id = collector.get_trace_by_id(t2_id)
    assert by_id is not None
    assert by_id.name == "op_beta"
