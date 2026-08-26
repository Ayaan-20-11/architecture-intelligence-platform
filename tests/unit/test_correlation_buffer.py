from datetime import UTC, datetime, timedelta

from app.telemetry.correlation_buffer import HttpCorrelationBuffer, PendingHttpSpan


def _pending(**overrides) -> PendingHttpSpan:
    defaults = {
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "parent_span_id": None,
        "span_kind": "CLIENT",
        "service_name": "OrderService",
        "service_namespace": None,
        "service_version": None,
        "environment": "production",
        "method": None,
        "route": None,
        "timestamp": datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return PendingHttpSpan(**defaults)


def test_offer_server_then_offer_client_matches():
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10)
    server = _pending(
        span_kind="SERVER",
        parent_span_id="c" * 16,
        service_name="ProductService",
        environment="production",
        method="GET",
        route="/products/{id}",
    )
    client = _pending(span_kind="CLIENT", span_id="c" * 16, service_name="OrderService")

    assert buffer.offer_server(server) is None
    matched = buffer.offer_client(client)

    assert matched is not None
    assert matched.service_name == "ProductService"
    assert buffer.cross_batch_matches == 1


def test_offer_client_then_offer_server_matches():
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10)
    client = _pending(span_kind="CLIENT", span_id="c" * 16, service_name="OrderService")
    server = _pending(
        span_kind="SERVER",
        parent_span_id="c" * 16,
        service_name="ProductService",
        environment="production",
        method="GET",
        route="/products/{id}",
    )

    assert buffer.offer_client(client) is None
    matched = buffer.offer_server(server)

    assert matched is not None
    assert matched.service_name == "OrderService"
    assert buffer.cross_batch_matches == 1


def test_different_trace_ids_never_match():
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10)
    client = _pending(span_kind="CLIENT", span_id="c" * 16, trace_id="a" * 32)
    server = _pending(
        span_kind="SERVER", parent_span_id="c" * 16, trace_id="z" * 32, environment="production"
    )

    assert buffer.offer_client(client) is None
    assert buffer.offer_server(server) is None
    assert buffer.cross_batch_matches == 0


def test_server_with_no_parent_span_id_is_never_buffered_or_matched():
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10)
    server = _pending(span_kind="SERVER", parent_span_id=None, environment="production")
    assert buffer.offer_server(server) is None
    # Nothing was buffered for it, so an otherwise-matching client still finds no counterpart.
    client = _pending(span_kind="CLIENT", span_id="c" * 16)
    assert buffer.offer_client(client) is None


def test_ttl_expiry_removes_a_stale_pending_entry():
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10)
    client = _pending(span_kind="CLIENT", span_id="c" * 16)
    assert buffer.offer_client(client) is None

    # Simulate time passing beyond the TTL by directly rewriting the stored insertion timestamp -
    # the buffer has no clock injection point, and this keeps the test deterministic and fast.
    key = (client.trace_id, client.span_id)
    stored_span, _ = buffer._pending_clients[key]
    buffer._pending_clients[key] = (stored_span, datetime.now(UTC) - timedelta(seconds=120))

    server = _pending(
        span_kind="SERVER",
        parent_span_id="c" * 16,
        environment="production",
        method="GET",
        route="/x",
    )
    matched = buffer.offer_server(server)

    assert matched is None
    assert buffer.expirations >= 1


def test_max_pending_spans_evicts_the_oldest_entry():
    buffer = HttpCorrelationBuffer(ttl_seconds=3600, max_pending_spans=2)
    buffer.offer_client(_pending(span_kind="CLIENT", span_id="1" * 16, trace_id="a" * 32))
    buffer.offer_client(_pending(span_kind="CLIENT", span_id="2" * 16, trace_id="a" * 32))
    buffer.offer_client(_pending(span_kind="CLIENT", span_id="3" * 16, trace_id="a" * 32))

    assert len(buffer._pending_clients) == 2
    assert buffer.evictions == 1
    # The oldest (span_id "1"...) was evicted - a server matching it now finds nothing.
    evicted_server = _pending(
        span_kind="SERVER",
        parent_span_id="1" * 16,
        trace_id="a" * 32,
        environment="production",
        method="GET",
        route="/x",
    )
    assert buffer.offer_server(evicted_server) is None
    # The two most recent (span_id "2"/"3") are still present.
    surviving_server = _pending(
        span_kind="SERVER",
        parent_span_id="3" * 16,
        trace_id="a" * 32,
        environment="production",
        method="GET",
        route="/x",
    )
    assert buffer.offer_server(surviving_server) is not None
