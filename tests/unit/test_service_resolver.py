from datetime import UTC, datetime

from app.telemetry.model import DiscoveryStatus, RuntimeSpan
from app.telemetry.service_resolver import (
    DeclaredServiceCandidate,
    resolve_runtime_span,
    resolve_service,
)

ORDER_SERVICE = DeclaredServiceCandidate(
    id="service:order-service", name="OrderService", namespace=None
)
PAYMENT_SERVICE = DeclaredServiceCandidate(
    id="service:payment-service", name="PaymentService", namespace=None
)
NAMESPACED = DeclaredServiceCandidate(
    id="service:commerce:fraud-service", name="FraudService", namespace="commerce"
)
DUPLICATE_NAME_A = DeclaredServiceCandidate(id="service:payment-v1", name="Payment", namespace=None)
DUPLICATE_NAME_B = DeclaredServiceCandidate(id="service:payment-v2", name="Payment", namespace=None)


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
        "environment": None,
        "start_time": datetime(2026, 8, 26, tzinfo=UTC),
        "end_time": datetime(2026, 8, 26, tzinfo=UTC),
    }
    defaults.update(overrides)
    return RuntimeSpan(**defaults)


# --- tier 1: namespace + name --------------------------------------------------------------------


def test_tier1_namespace_and_name_match():
    result = resolve_service(
        [NAMESPACED],
        service_name="FraudService",
        service_namespace="commerce",
        aliases={},
    )
    assert result.service_id == "service:commerce:fraud-service"
    assert result.discovery_status == DiscoveryStatus.DECLARED


def test_tier1_mismatched_namespace_falls_through_to_tier2_name_match():
    # Tier 1 itself doesn't match (wrong namespace), but tier 2's plain name match still finds
    # the same candidate by name alone - tier 2 is intentionally namespace-agnostic.
    result = resolve_service(
        [NAMESPACED],
        service_name="FraudService",
        service_namespace="other-namespace",
        aliases={},
    )
    assert result.service_id == "service:commerce:fraud-service"
    assert result.discovery_status == DiscoveryStatus.DECLARED


def test_no_match_at_any_tier_is_observed_only():
    result = resolve_service(
        [ORDER_SERVICE, PAYMENT_SERVICE],
        service_name="FraudService",
        service_namespace="other-namespace",
        aliases={},
    )
    assert result.discovery_status == DiscoveryStatus.OBSERVED_ONLY
    assert result.service_id == "service:other-namespace:fraudservice"


# --- tier 2: name alone ----------------------------------------------------------------------------


def test_tier2_exact_name_match():
    result = resolve_service(
        [ORDER_SERVICE, PAYMENT_SERVICE],
        service_name="PaymentService",
        service_namespace=None,
        aliases={},
    )
    assert result.service_id == "service:payment-service"
    assert result.discovery_status == DiscoveryStatus.DECLARED


def test_tier2_does_not_guess_when_multiple_candidates_share_a_name():
    result = resolve_service(
        [DUPLICATE_NAME_A, DUPLICATE_NAME_B],
        service_name="Payment",
        service_namespace=None,
        aliases={},
    )
    assert result.discovery_status == DiscoveryStatus.OBSERVED_ONLY


# --- tier 3: alias -----------------------------------------------------------------------------------


def test_tier3_configured_alias():
    result = resolve_service(
        [ORDER_SERVICE],
        service_name="legacy-order-svc",
        service_namespace=None,
        aliases={"legacy-order-svc": "service:order-service"},
    )
    assert result.service_id == "service:order-service"
    assert result.discovery_status == DiscoveryStatus.DECLARED


# --- tier 4: observed-only --------------------------------------------------------------------------


def test_tier4_observed_only_mints_deterministic_id():
    result = resolve_service(
        [ORDER_SERVICE], service_name="FraudService", service_namespace=None, aliases={}
    )
    assert result.service_id == "service:fraudservice"
    assert result.discovery_status == DiscoveryStatus.OBSERVED_ONLY
    # deterministic - same input always mints the same id
    again = resolve_service(
        [ORDER_SERVICE], service_name="FraudService", service_namespace=None, aliases={}
    )
    assert again.service_id == result.service_id


def test_tier4_observed_only_includes_namespace_when_present():
    result = resolve_service(
        [], service_name="FraudService", service_namespace="commerce", aliases={}
    )
    assert result.service_id == "service:commerce:fraudservice"
    assert result.discovery_status == DiscoveryStatus.OBSERVED_ONLY


# --- resolve_runtime_span: environment + instance-id-ignored (spec §61 "instance ignored") --------


def test_resolve_runtime_span_folds_in_environment():
    span = _span(service_name="OrderService", environment="production")
    result = resolve_runtime_span([ORDER_SERVICE], span, aliases={})
    assert result.service_id == "service:order-service"
    assert result.discovery_status == DiscoveryStatus.DECLARED
    assert result.environment == "production"


def test_service_instance_id_is_ignored_by_resolution():
    span_a = _span(service_name="OrderService", service_instance_id="pod-1")
    span_b = _span(service_name="OrderService", service_instance_id="pod-2")
    result_a = resolve_runtime_span([ORDER_SERVICE], span_a, aliases={})
    result_b = resolve_runtime_span([ORDER_SERVICE], span_b, aliases={})
    assert result_a.service_id == result_b.service_id == "service:order-service"
