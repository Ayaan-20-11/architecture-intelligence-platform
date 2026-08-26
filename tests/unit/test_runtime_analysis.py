from datetime import UTC, datetime, timedelta

from app.analysis.runtime import (
    COVERAGE_NONE,
    COVERAGE_PARTIAL,
    COVERAGE_SUFFICIENT,
    COVERAGE_UNKNOWN,
    DEFAULT_WINDOW_HOURS,
    ServiceTelemetryCoverage,
    _classify_coverage,
    default_since,
)


def test_default_since_uses_the_default_window():
    before = datetime.now(UTC)
    since = default_since()
    after = datetime.now(UTC)

    assert before - timedelta(hours=DEFAULT_WINDOW_HOURS) <= since
    assert since <= after - timedelta(hours=DEFAULT_WINDOW_HOURS)


def test_default_since_honors_a_custom_window():
    now = datetime.now(UTC)
    since = default_since(hours=1)

    assert now - since <= timedelta(hours=1, seconds=5)


# --- coverage qualification (11H-E) --------------------------------------------------------------


def _coverage(**overrides) -> ServiceTelemetryCoverage:
    defaults = {
        "service_id": "service:order-service",
        "service_name": "OrderService",
        "environment": "production",
        "since": datetime(2026, 8, 26, tzinfo=UTC),
        "http_observed": False,
        "messaging_observed": False,
        "spans_observed": False,
    }
    defaults.update(overrides)
    return ServiceTelemetryCoverage(**defaults)


def test_classify_coverage_is_unknown_when_qualification_disabled():
    coverage = _coverage(http_observed=True, spans_observed=True)
    assert _classify_coverage(coverage, "CALLS", qualification_enabled=False) == COVERAGE_UNKNOWN


def test_classify_coverage_is_unknown_when_no_coverage_row_exists():
    assert _classify_coverage(None, "CALLS", qualification_enabled=True) == COVERAGE_UNKNOWN


def test_classify_coverage_is_sufficient_when_the_same_relation_kind_is_observed():
    calls_coverage = _coverage(http_observed=True, spans_observed=True)
    assert _classify_coverage(calls_coverage, "CALLS", qualification_enabled=True) == (
        COVERAGE_SUFFICIENT
    )

    messaging_coverage = _coverage(messaging_observed=True, spans_observed=True)
    assert (
        _classify_coverage(messaging_coverage, "SENDS", qualification_enabled=True)
        == COVERAGE_SUFFICIENT
    )
    assert (
        _classify_coverage(messaging_coverage, "RECEIVES_FROM", qualification_enabled=True)
        == COVERAGE_SUFFICIENT
    )


def test_classify_coverage_is_partial_when_a_different_kind_is_observed():
    # HTTP is instrumented, but this row is a messaging relation - weaker evidence, not none.
    coverage = _coverage(http_observed=True, spans_observed=True)
    assert _classify_coverage(coverage, "SENDS", qualification_enabled=True) == COVERAGE_PARTIAL


def test_classify_coverage_is_none_when_nothing_was_observed_at_all():
    coverage = _coverage()
    assert _classify_coverage(coverage, "CALLS", qualification_enabled=True) == COVERAGE_NONE
