from datetime import UTC, datetime

from app.telemetry.adapter import NO_ENVIRONMENT, NO_STABLE_ROUTE, correlate_http_call_observations
from app.telemetry.model import RuntimeSpan
from app.telemetry.operation_resolver import DeclaredOperationCandidate
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
