from datetime import UTC, datetime

from app.telemetry.adapter import (
    CORRELATION_EXPIRED,
    MISSING_CALLER_IDENTITY,
    MISSING_TARGET_IDENTITY,
    NO_DESTINATION_NAME,
    NO_ENVIRONMENT,
    NO_STABLE_ROUTE,
    adapt,
    correlate_http_call_observations,
    correlate_queue_observations,
)
from app.telemetry.correlation_buffer import HttpCorrelationBuffer
from app.telemetry.model import RuntimeSpan
from app.telemetry.operation_resolver import DeclaredOperationCandidate
from app.telemetry.queue_resolver import DeclaredQueueCandidate
from app.telemetry.service_resolver import DeclaredServiceCandidate

ORDER_SERVICE = DeclaredServiceCandidate(
    id="service:order-service", name="OrderService", namespace=None
)
PRODUCT_SERVICE = DeclaredServiceCandidate(
    id="service:product-service", name="ProductService", namespace=None
)
SERVICE_CANDIDATES = [ORDER_SERVICE, PRODUCT_SERVICE]

GET_PRODUCT = DeclaredOperationCandidate(
    id="operation:product-service:GET:/products/{id}",
    provider_service_id="service:product-service",
    method="GET",
    path="/products/{id}",
)
OPERATION_CANDIDATES = [GET_PRODUCT]

PAYMENT_Q = DeclaredQueueCandidate(id="queue:payment-q", name="payment-q", namespace=None)
QUEUE_CANDIDATES = [PAYMENT_Q]


def _span(**overrides) -> RuntimeSpan:
    defaults = {
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "parent_span_id": None,
        "span_name": "op",
        "span_kind": "CLIENT",
        "service_name": "OrderService",
        "service_namespace": None,
        "service_version": None,
        "service_instance_id": None,
        "environment": "production",
        "start_time": datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
        "end_time": datetime(2026, 8, 26, 12, 0, 1, tzinfo=UTC),
        "attributes": {},
    }
    defaults.update(overrides)
    return RuntimeSpan(**defaults)


def _client_server_pair(**server_overrides):
    client = _span(
        span_id="c1" * 8,
        span_kind="CLIENT",
        service_name="OrderService",
        service_version="1.0.0",
    )
    server_defaults = {
        "parent_span_id": client.span_id,
        "span_kind": "SERVER",
        "service_name": "ProductService",
        "attributes": {"http.request.method": "GET", "http.route": "/products/{id}"},
    }
    server_defaults.update(server_overrides)
    server = _span(**server_defaults)
    return client, server


def _correlate(spans, **kwargs):
    return correlate_http_call_observations(
        spans,
        service_candidates=kwargs.get("service_candidates", SERVICE_CANDIDATES),
        operation_candidates=kwargs.get("operation_candidates", OPERATION_CANDIDATES),
        service_aliases=kwargs.get("service_aliases", {}),
        correlation_buffer=kwargs.get("correlation_buffer"),
    )


# --- correlation pairing -----------------------------------------------------------------------


def test_correlated_pair_produces_one_calls_fact():
    client, server = _client_server_pair()
    batch = _correlate([client, server])
    assert len(batch.facts) == 1
    fact = batch.facts[0]
    assert fact.subject_id == "service:order-service"
    assert fact.relation_type == "CALLS"
    assert fact.object_id == "operation:product-service:GET:/products/{id}"
    assert fact.environment == "production"
    assert batch.unresolved == []


def test_unpaired_client_only_produces_empty_batch():
    client, _ = _client_server_pair()
    batch = _correlate([client])
    assert batch.facts == []
    assert batch.entities == []
    assert batch.unresolved == []


def test_unpaired_server_only_produces_empty_batch():
    _, server = _client_server_pair()
    batch = _correlate([server])
    assert batch.facts == []


def test_mismatched_trace_id_does_not_correlate():
    client, server = _client_server_pair()
    client = client.model_copy(update={"trace_id": "z" * 32})
    batch = _correlate([client, server])
    assert batch.facts == []


def test_empty_batch_of_spans_produces_empty_observation_batch():
    batch = _correlate([])
    assert batch.facts == []
    assert batch.entities == []
    assert batch.unresolved == []


# --- cross-batch correlation (11H-B) ---------------------------------------------------------


def test_cross_batch_server_first_then_client_produces_one_calls_fact():
    client, server = _client_server_pair()
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)

    first = _correlate([server], correlation_buffer=buffer)
    assert first.facts == []

    second = _correlate([client], correlation_buffer=buffer)
    assert len(second.facts) == 1
    fact = second.facts[0]
    assert fact.subject_id == "service:order-service"
    assert fact.object_id == "operation:product-service:GET:/products/{id}"
    assert fact.environment == "production"
    assert buffer.cross_batch_matches == 1


def test_cross_batch_client_first_then_server_produces_one_calls_fact():
    client, server = _client_server_pair()
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)

    first = _correlate([client], correlation_buffer=buffer)
    assert first.facts == []

    second = _correlate([server], correlation_buffer=buffer)
    assert len(second.facts) == 1
    fact = second.facts[0]
    assert fact.subject_id == "service:order-service"
    assert fact.object_id == "operation:product-service:GET:/products/{id}"
    assert buffer.cross_batch_matches == 1


def test_buffer_none_preserves_single_batch_only_behavior():
    client, server = _client_server_pair()
    first = _correlate([client], correlation_buffer=None)
    second = _correlate([server], correlation_buffer=None)
    assert first.facts == []
    assert second.facts == []


def test_leftover_server_missing_route_is_unresolved_not_buffered():
    _, server = _client_server_pair(attributes={})
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    batch = _correlate([server], correlation_buffer=buffer)
    assert [u.reason for u in batch.unresolved] == [NO_STABLE_ROUTE]
    assert buffer.cross_batch_matches == 0


def test_cross_batch_correlated_pair_has_client_server_correlation_mode():
    client, server = _client_server_pair()
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([client], correlation_buffer=buffer)
    batch = _correlate([server], correlation_buffer=buffer)
    assert batch.facts[0].evidence.correlation_mode == "CLIENT_SERVER"


def test_in_batch_correlated_pair_has_client_server_correlation_mode():
    client, server = _client_server_pair()
    batch = _correlate([client, server])
    assert batch.facts[0].evidence.correlation_mode == "CLIENT_SERVER"


# --- partial instrumentation: CLIENT_ONLY / SERVER_ONLY (11H-C) -------------------------------


def _expire_client(buffer, client):
    key = (client.trace_id, client.span_id)
    stored_span, _ = buffer._pending_clients[key]
    buffer._pending_clients[key] = (stored_span, datetime(2000, 1, 1, tzinfo=UTC))


def _expire_server(buffer, server):
    key = (server.trace_id, server.parent_span_id)
    stored_span, _ = buffer._pending_servers[key]
    buffer._pending_servers[key] = (stored_span, datetime(2000, 1, 1, tzinfo=UTC))


def test_client_only_with_peer_service_produces_a_calls_fact():
    client = _span(
        span_kind="CLIENT",
        attributes={
            "http.request.method": "GET",
            "http.route": "/products/{id}",
            "peer.service": "ProductService",
        },
    )
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([client], correlation_buffer=buffer)
    _expire_client(buffer, client)

    batch = _correlate([], correlation_buffer=buffer)

    assert len(batch.facts) == 1
    fact = batch.facts[0]
    assert fact.subject_id == "service:order-service"
    assert fact.object_id == "operation:product-service:GET:/products/{id}"
    assert fact.evidence.correlation_mode == "CLIENT_ONLY"
    assert batch.unresolved == []


def test_client_only_without_peer_service_is_unresolved():
    client = _span(
        span_kind="CLIENT",
        attributes={"http.request.method": "GET", "http.route": "/products/{id}"},
    )
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([client], correlation_buffer=buffer)
    _expire_client(buffer, client)

    batch = _correlate([], correlation_buffer=buffer)

    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [MISSING_TARGET_IDENTITY]


def test_client_only_without_method_or_route_is_correlation_expired():
    client = _span(span_kind="CLIENT", attributes={"peer.service": "ProductService"})
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([client], correlation_buffer=buffer)
    _expire_client(buffer, client)

    batch = _correlate([], correlation_buffer=buffer)

    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [CORRELATION_EXPIRED]


def test_client_only_without_environment_is_unresolved():
    client = _span(
        span_kind="CLIENT",
        environment=None,
        attributes={
            "http.request.method": "GET",
            "http.route": "/products/{id}",
            "peer.service": "ProductService",
        },
    )
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([client], correlation_buffer=buffer)
    _expire_client(buffer, client)

    batch = _correlate([], correlation_buffer=buffer)

    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [NO_ENVIRONMENT]


def test_server_only_never_invents_a_caller():
    _, server = _client_server_pair(service_name="FraudService")
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([server], correlation_buffer=buffer)
    _expire_server(buffer, server)

    batch = _correlate([], correlation_buffer=buffer)

    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [MISSING_CALLER_IDENTITY]
    # The provider itself is still recorded as an observed-only entity, even with no caller.
    assert any(e.label == "Service" and e.name == "FraudService" for e in batch.entities)


# --- unresolved reasons --------------------------------------------------------------------------


def test_missing_environment_is_unresolved():
    client, server = _client_server_pair(environment=None)
    batch = _correlate([client, server])
    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [NO_ENVIRONMENT]


def test_missing_route_is_unresolved():
    client, server = _client_server_pair(attributes={"http.request.method": "GET"})
    batch = _correlate([client, server])
    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [NO_STABLE_ROUTE]


def test_all_unresolved_reasons_are_from_the_fixed_set():
    client_a, server_a = _client_server_pair(environment=None)
    client_b, server_b = _client_server_pair(
        span_id="c2" * 8, attributes={"http.request.method": "GET"}
    )
    server_b = server_b.model_copy(update={"parent_span_id": client_b.span_id})
    batch = _correlate([client_a, server_a, client_b, server_b])
    assert {u.reason for u in batch.unresolved} <= {NO_ENVIRONMENT, NO_STABLE_ROUTE}
    assert len(batch.unresolved) == 2


# --- evidence shape --------------------------------------------------------------------------------


def test_evidence_has_opentelemetry_defaults_and_single_observation_seed():
    client, server = _client_server_pair()
    fact = _correlate([client, server]).facts[0]
    evidence = fact.evidence
    assert evidence.source_type == "OPENTELEMETRY"
    assert evidence.evidence_type == "OBSERVED"
    assert evidence.source_file == "opentelemetry"
    assert evidence.observation_count == 1
    assert evidence.sample_trace_ids == [server.trace_id]
    assert evidence.first_seen == evidence.last_seen == fact.timestamp
    assert evidence.bucket_start <= fact.timestamp < evidence.bucket_end


def test_evidence_id_is_deterministic_for_the_same_fact():
    client, server = _client_server_pair()
    fact1 = _correlate([client, server]).facts[0]
    fact2 = _correlate([client, server]).facts[0]
    assert fact1.evidence.id == fact2.evidence.id


def test_source_service_version_comes_from_client_span():
    client, server = _client_server_pair()
    fact = _correlate([client, server]).facts[0]
    assert fact.source_service_version == "1.0.0"


# --- observed-only entities ------------------------------------------------------------------------


def test_observed_only_provider_and_operation_are_recorded_as_entities():
    client, server = _client_server_pair(service_name="FraudService")
    batch = _correlate([client, server])
    labels_and_ids = {(e.label, e.id) for e in batch.entities}
    assert ("Service", "service:fraudservice") in labels_and_ids
    # the operation is minted observed-only too, since FraudService has no declared operations
    assert any(label == "Operation" for label, _ in labels_and_ids)


def test_declared_provider_and_operation_are_not_recorded_as_entities():
    client, server = _client_server_pair()
    batch = _correlate([client, server])
    assert batch.entities == []


def test_observed_only_entities_are_deduplicated_across_pairs():
    client_a, server_a = _client_server_pair(service_name="FraudService")
    client_b, server_b = _client_server_pair(span_id="c2" * 8, service_name="FraudService")
    server_b = server_b.model_copy(update={"parent_span_id": client_b.span_id})
    batch = _correlate([client_a, server_a, client_b, server_b])
    service_entities = [e for e in batch.entities if e.label == "Service"]
    assert len(service_entities) == 1


# --- correlate_queue_observations ---------------------------------------------------------------


def _queue_correlate(spans, **kwargs):
    return correlate_queue_observations(
        spans,
        service_candidates=kwargs.get("service_candidates", SERVICE_CANDIDATES),
        queue_candidates=kwargs.get("queue_candidates", QUEUE_CANDIDATES),
        service_aliases=kwargs.get("service_aliases", {}),
        queue_aliases=kwargs.get("queue_aliases", {}),
    )


def test_send_span_produces_sends_fact():
    span = _span(
        service_name="OrderService",
        attributes={
            "messaging.system": "azure.servicebus",
            "messaging.operation.type": "send",
            "messaging.destination.name": "payment-q",
        },
    )
    batch = _queue_correlate([span])
    assert len(batch.facts) == 1
    fact = batch.facts[0]
    assert fact.subject_id == "service:order-service"
    assert fact.relation_type == "SENDS"
    assert fact.object_id == "queue:payment-q"
    assert fact.evidence.correlation_mode == "MESSAGING_SEND"
    assert batch.unresolved == []


def test_receive_span_produces_receives_from_fact():
    span = _span(
        service_name="PaymentService",
        attributes={
            "messaging.operation.type": "receive",
            "messaging.destination.name": "payment-q",
        },
    )
    batch = _queue_correlate([span])
    assert batch.facts[0].relation_type == "RECEIVES_FROM"
    assert batch.facts[0].evidence.correlation_mode == "MESSAGING_RECEIVE"


def test_process_span_produces_receives_from_fact():
    span = _span(
        service_name="PaymentService",
        attributes={
            "messaging.operation.type": "process",
            "messaging.destination.name": "payment-q",
        },
    )
    batch = _queue_correlate([span])
    assert batch.facts[0].relation_type == "RECEIVES_FROM"
    assert batch.facts[0].evidence.correlation_mode == "MESSAGING_PROCESS"


def test_unrecognized_operation_type_is_silently_skipped():
    span = _span(
        attributes={"messaging.operation.type": "create", "messaging.destination.name": "payment-q"}
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.unresolved == []


def test_missing_operation_type_is_silently_skipped():
    span = _span(attributes={"messaging.destination.name": "payment-q"})
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.unresolved == []


def test_missing_destination_name_is_unresolved():
    span = _span(attributes={"messaging.operation.type": "send"})
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [NO_DESTINATION_NAME]


def test_missing_environment_is_unresolved_for_queue_observations():
    span = _span(
        environment=None,
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [NO_ENVIRONMENT]


def test_observed_only_service_and_queue_are_both_recorded():
    span = _span(
        service_name="FraudService",
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "legacy-q"},
    )
    batch = _queue_correlate([span])
    labels = {e.label for e in batch.entities}
    assert labels == {"Service", "Queue"}


def test_queue_evidence_matches_the_single_observation_seed_shape():
    span = _span(
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"}
    )
    fact = _queue_correlate([span]).facts[0]
    evidence = fact.evidence
    assert evidence.source_type == "OPENTELEMETRY"
    assert evidence.evidence_type == "OBSERVED"
    assert evidence.observation_count == 1
    assert evidence.sample_trace_ids == [span.trace_id]


# --- adapt: combines HTTP and queue observations ------------------------------------------------


def test_adapt_combines_http_and_queue_facts():
    client, server = _client_server_pair()
    queue_span = _span(
        span_id="q1" * 8,
        service_name="OrderService",
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = adapt(
        [client, server, queue_span],
        service_candidates=SERVICE_CANDIDATES,
        operation_candidates=OPERATION_CANDIDATES,
        queue_candidates=QUEUE_CANDIDATES,
        service_aliases={},
        queue_aliases={},
    )
    relation_types = {f.relation_type for f in batch.facts}
    assert relation_types == {"CALLS", "SENDS"}


def test_adapt_deduplicates_entities_discovered_via_both_paths():
    client, server = _client_server_pair(service_name="FraudService")
    queue_span = _span(
        span_id="q2" * 8,
        service_name="FraudService",
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = adapt(
        [client, server, queue_span],
        service_candidates=SERVICE_CANDIDATES,
        operation_candidates=OPERATION_CANDIDATES,
        queue_candidates=QUEUE_CANDIDATES,
        service_aliases={},
        queue_aliases={},
    )
    fraud_entities = [e for e in batch.entities if e.name == "FraudService"]
    assert len(fraud_entities) == 1
