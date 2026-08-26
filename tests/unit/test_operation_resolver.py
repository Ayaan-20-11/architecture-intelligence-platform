from app.telemetry.model import DiscoveryStatus
from app.telemetry.operation_resolver import DeclaredOperationCandidate, resolve_operation

GET_PRODUCT = DeclaredOperationCandidate(
    id="operation:product-service:GET:/products/{id}",
    provider_service_id="service:product-service",
    method="GET",
    path="/products/{id}",
)


def test_fall_a_matches_declared_operation():
    result = resolve_operation(
        [GET_PRODUCT],
        provider_service_id="service:product-service",
        method="GET",
        route="/products/{id}",
    )
    assert result.operation_id == "operation:product-service:GET:/products/{id}"
    assert result.discovery_status == DiscoveryStatus.DECLARED


def test_fall_a_method_matching_is_case_insensitive():
    result = resolve_operation(
        [GET_PRODUCT],
        provider_service_id="service:product-service",
        method="get",
        route="/products/{id}",
    )
    assert result.discovery_status == DiscoveryStatus.DECLARED


def test_fall_b_mints_observed_only_operation_id():
    result = resolve_operation(
        [GET_PRODUCT],
        provider_service_id="service:fraudservice",
        method="GET",
        route="/internal/products/{id}",
    )
    assert result.operation_id == "operation:service:fraudservice:GET:/internal/products/{id}"
    assert result.discovery_status == DiscoveryStatus.OBSERVED_ONLY
    # visually distinct from a declared operation id (bare slug, not a full service id)
    assert result.operation_id != GET_PRODUCT.id


def test_fall_b_wrong_provider_does_not_match_declared():
    # Same method+path as GET_PRODUCT, but a different provider - must not match Fall A.
    result = resolve_operation(
        [GET_PRODUCT],
        provider_service_id="service:order-service",
        method="GET",
        route="/products/{id}",
    )
    assert result.discovery_status == DiscoveryStatus.OBSERVED_ONLY


def test_fall_c_no_route_is_unresolved():
    result = resolve_operation(
        [GET_PRODUCT], provider_service_id="service:product-service", method="GET", route=None
    )
    assert result.operation_id is None
    assert result.discovery_status is None


def test_fall_c_empty_route_is_unresolved():
    result = resolve_operation(
        [GET_PRODUCT], provider_service_id="service:product-service", method="GET", route=""
    )
    assert result.operation_id is None
    assert result.discovery_status is None
