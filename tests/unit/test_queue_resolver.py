from app.telemetry.model import DiscoveryStatus
from app.telemetry.queue_resolver import DeclaredQueueCandidate, resolve_queue

PAYMENT_Q = DeclaredQueueCandidate(id="queue:payment-q", name="payment-q", namespace=None)
NAMESPACED_Q = DeclaredQueueCandidate(id="queue:kafka:orders-q", name="orders-q", namespace="kafka")
DUPLICATE_A = DeclaredQueueCandidate(id="queue:events-v1", name="events", namespace=None)
DUPLICATE_B = DeclaredQueueCandidate(id="queue:events-v2", name="events", namespace=None)


def test_system_and_name_exact_match():
    result = resolve_queue(
        [NAMESPACED_Q], messaging_system="kafka", destination_name="orders-q", aliases={}
    )
    assert result.queue_id == "queue:kafka:orders-q"
    assert result.discovery_status == DiscoveryStatus.DECLARED


def test_bare_name_match_when_system_does_not_match():
    # payment-q has no namespace, so the system-qualified tier can't match it - falls through to
    # the bare-name tier, which is what actually unifies AsyncAPI-declared and OTel-observed queues
    # today (spec §27).
    result = resolve_queue(
        [PAYMENT_Q], messaging_system="azure.servicebus", destination_name="payment-q", aliases={}
    )
    assert result.queue_id == "queue:payment-q"
    assert result.discovery_status == DiscoveryStatus.DECLARED


def test_bare_name_collision_does_not_guess():
    result = resolve_queue(
        [DUPLICATE_A, DUPLICATE_B], messaging_system=None, destination_name="events", aliases={}
    )
    assert result.discovery_status == DiscoveryStatus.OBSERVED_ONLY


def test_alias_fallback():
    result = resolve_queue(
        [PAYMENT_Q],
        messaging_system=None,
        destination_name="legacy-payment-queue",
        aliases={"legacy-payment-queue": "queue:payment-q"},
    )
    assert result.queue_id == "queue:payment-q"
    assert result.discovery_status == DiscoveryStatus.DECLARED


def test_observed_only_mint_includes_messaging_system():
    result = resolve_queue(
        [PAYMENT_Q], messaging_system="kafka", destination_name="unknown-q", aliases={}
    )
    assert result.queue_id == "queue:kafka:unknown-q"
    assert result.discovery_status == DiscoveryStatus.OBSERVED_ONLY


def test_observed_only_mint_without_messaging_system():
    result = resolve_queue(
        [PAYMENT_Q], messaging_system=None, destination_name="unknown-q", aliases={}
    )
    assert result.queue_id == "queue:unknown-q"
    assert result.discovery_status == DiscoveryStatus.OBSERVED_ONLY


def test_missing_messaging_system_skips_tier_one_gracefully():
    # No exception, no false match - just falls straight to the bare-name tier.
    result = resolve_queue(
        [PAYMENT_Q], messaging_system=None, destination_name="payment-q", aliases={}
    )
    assert result.queue_id == "queue:payment-q"
    assert result.discovery_status == DiscoveryStatus.DECLARED
