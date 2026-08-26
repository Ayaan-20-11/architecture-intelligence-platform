from datetime import UTC, datetime
from pathlib import Path

import pytest
from testcontainers.community.neo4j import Neo4jContainer

from app.analysis.runtime import (
    NOT_OBSERVED_IN_WINDOW,
    confirmed_relations,
    declared_only_relations,
    observed_only_relations,
    observed_relations,
    service_runtime_profile,
    telemetry_coverage,
)
from app.canonical import ids
from app.graph.importer import import_all_sources
from app.provenance.model import ObservedEvidence
from app.telemetry.aggregator import persist_observation_batch
from app.telemetry.model import ObservationBatch, ObservedFactCandidate, ObservedOnlyEntity

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
DATABASE = "neo4j"
SINCE = datetime(2026, 8, 26, 0, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def neo4j_container():
    with Neo4jContainer("neo4j:5") as container:
        yield container


@pytest.fixture(scope="module")
def driver(neo4j_container):
    drv = neo4j_container.get_driver()
    yield drv
    drv.close()


@pytest.fixture(scope="module", autouse=True)
def populated_graph(driver):
    with driver.session(database=DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n")
    import_all_sources(driver, database=DATABASE, root=EXAMPLES_DIR)


@pytest.fixture
def session(driver):
    with driver.session(database=DATABASE) as s:
        yield s


def _fact(
    *,
    subject_id: str,
    relation_type: str,
    object_id: str,
    environment: str,
    timestamp: datetime = datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
    trace_id: str = "a" * 32,
    observation_count: int = 1,
) -> ObservedFactCandidate:
    evidence = ObservedEvidence(
        id=ids.observed_evidence_id(
            environment, datetime(2026, 8, 26, tzinfo=UTC), subject_id, relation_type, object_id
        ),
        environment=environment,
        bucket_start=datetime(2026, 8, 26, tzinfo=UTC),
        bucket_end=datetime(2026, 8, 27, tzinfo=UTC),
        first_seen=timestamp,
        last_seen=timestamp,
        observation_count=observation_count,
        sample_trace_ids=[trace_id],
    )
    return ObservedFactCandidate(
        subject_id=subject_id,
        relation_type=relation_type,
        object_id=object_id,
        environment=environment,
        timestamp=timestamp,
        trace_id=trace_id,
        evidence=evidence,
    )


def _persist(driver, *facts, entities=()):
    persist_observation_batch(
        driver, DATABASE, ObservationBatch(entities=list(entities), facts=list(facts))
    )


# --- O1: observed relations, aggregation and filters --------------------------------------------


def test_o1_aggregates_multiple_observations_of_the_same_relation(driver, session):
    subject_id = ids.service_id("order-service")
    object_id = ids.queue_id("payment-q")
    first = _fact(
        subject_id=subject_id,
        relation_type="SENDS",
        object_id=object_id,
        environment="o1-env",
        timestamp=datetime(2026, 8, 26, 8, 0, tzinfo=UTC),
        trace_id="1" * 32,
    )
    second = _fact(
        subject_id=subject_id,
        relation_type="SENDS",
        object_id=object_id,
        environment="o1-env",
        timestamp=datetime(2026, 8, 26, 18, 0, tzinfo=UTC),
        trace_id="2" * 32,
    )
    _persist(driver, first, second)

    results = observed_relations(session, environment="o1-env", since=SINCE)
    assert len(results) == 1
    row = results[0]
    assert row.source_id == subject_id
    assert row.target_id == object_id
    assert row.observation_count == 2
    assert row.first_seen == datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    assert row.last_seen == datetime(2026, 8, 26, 18, 0, tzinfo=UTC)


def test_o1_filters_by_relation_type_and_from_id(driver, session):
    subject_id = ids.service_id("order-service")
    _persist(
        driver,
        _fact(
            subject_id=subject_id,
            relation_type="SENDS",
            object_id=ids.queue_id("payment-q"),
            environment="o1-filter-env",
        ),
    )

    matching = observed_relations(
        session,
        environment="o1-filter-env",
        relation_type="SENDS",
        from_id=subject_id,
        since=SINCE,
    )
    assert len(matching) == 1

    none_matching = observed_relations(
        session, environment="o1-filter-env", relation_type="CALLS", since=SINCE
    )
    assert none_matching == []


# --- O2: confirmed relations --------------------------------------------------------------------


def test_o2_finds_the_real_declared_relation_once_observed_too(driver, session):
    subject_id = ids.service_id("order-service")
    operation_id = ids.operation_id(ids.service_id("product-service"), "GET", "/products/{id}")
    provider_id = ids.service_id("product-service")
    _persist(
        driver,
        _fact(
            subject_id=subject_id,
            relation_type="CALLS",
            object_id=operation_id,
            environment="o2-env",
        ),
    )

    results = confirmed_relations(session, environment="o2-env", since=SINCE)
    # target_id resolves through the declared PROVIDES edge to the provider service, not the
    # raw operation id - that's the coalesce(provider.id, o.id) design this iteration relies on.
    assert any(r.source_id == subject_id and r.target_id == provider_id for r in results)


def test_o2_is_scoped_by_environment(driver, session):
    # Same fact as above, but a different environment never observed it - must not appear.
    results = confirmed_relations(session, environment="o2-env-unused", since=SINCE)
    subject_id = ids.service_id("order-service")
    provider_id = ids.service_id("product-service")
    assert not any(r.source_id == subject_id and r.target_id == provider_id for r in results)


# --- O3: observed-only relations, including a genuinely undeclared (no PROVIDES) operation ------


def test_o3_surfaces_a_relation_with_no_declared_evidence_at_all(driver, session):
    subject_id = ids.service_id("order-service")
    object_id = ids.queue_id("some-undeclared-queue")
    entity = ObservedOnlyEntity(id=object_id, label="Queue", name="some-undeclared-queue")
    _persist(
        driver,
        _fact(
            subject_id=subject_id, relation_type="SENDS", object_id=object_id, environment="o3-env"
        ),
        entities=[entity],
    )

    results = observed_only_relations(session, environment="o3-env", since=SINCE)
    assert any(r.source_id == subject_id and r.target_id == object_id for r in results)


def test_o3_resolves_target_identity_for_an_undeclared_operation_with_no_provides_edge(
    driver, session
):
    # Proves the OPTIONAL MATCH/coalesce() fix actually matters: this operation has no PROVIDES
    # edge at all (Fall B never writes one), so an inner join through PROVIDES would silently drop
    # this row entirely - exactly the case O3 exists to surface.
    subject_id = ids.service_id("order-service")
    provider_id = ids.service_id("product-service")
    object_id = ids.operation_id(provider_id, "GET", "/legacy/pricing")
    entity = ObservedOnlyEntity(id=object_id, label="Operation", name="GET /legacy/pricing")
    _persist(
        driver,
        _fact(
            subject_id=subject_id,
            relation_type="CALLS",
            object_id=object_id,
            environment="o3-gap-env",
        ),
        entities=[entity],
    )

    results = observed_only_relations(session, environment="o3-gap-env", since=SINCE)
    assert len(results) == 1
    assert results[0].target_id == object_id
    assert results[0].target_name == "GET /legacy/pricing"

    # sanity check: this operation genuinely has no PROVIDES edge in the graph
    count = session.run(
        "MATCH (:Operation {id: $id})<-[:PROVIDES]-() RETURN count(*) AS c", id=object_id
    ).single()["c"]
    assert count == 0


# --- O4: declared-only relations, status vocabulary, and coverage -------------------------------


def test_o4_reports_not_observed_in_window_with_no_coverage(driver, session):
    subject_id = ids.service_id("payment-service")
    object_id = ids.queue_id("invoice-q")

    results = declared_only_relations(session, environment="o4-env-nocoverage", since=SINCE)
    row = next(r for r in results if r.source_id == subject_id and r.target_id == object_id)
    assert row.status == NOT_OBSERVED_IN_WINDOW
    assert row.status == "NOT_OBSERVED_IN_WINDOW"  # pin the literal spec §40 vocabulary directly
    assert row.telemetry_coverage_available is False


def test_o4_reports_coverage_available_when_the_subject_has_other_observed_traffic(driver, session):
    subject_id = ids.service_id("payment-service")
    # Some unrelated observed SENDS from payment-service, in the same environment/window, gives
    # payment-service messaging coverage even though THIS specific relation is still unobserved.
    _persist(
        driver,
        _fact(
            subject_id=subject_id,
            relation_type="SENDS",
            object_id=ids.queue_id("some-other-queue"),
            environment="o4-env-coverage",
        ),
        entities=[ObservedOnlyEntity(id=ids.queue_id("some-other-queue"), label="Queue", name="x")],
    )

    object_id = ids.queue_id("invoice-q")
    results = declared_only_relations(session, environment="o4-env-coverage", since=SINCE)
    row = next(r for r in results if r.source_id == subject_id and r.target_id == object_id)
    assert row.status == NOT_OBSERVED_IN_WINDOW
    assert row.telemetry_coverage_available is True


# --- O5: telemetry coverage ----------------------------------------------------------------------


def test_o5_reports_http_observed_for_a_caller(driver, session):
    subject_id = ids.service_id("order-service")
    _persist(
        driver,
        _fact(
            subject_id=subject_id,
            relation_type="CALLS",
            object_id=ids.operation_id(ids.service_id("product-service"), "GET", "/products/{id}"),
            environment="o5-env",
        ),
    )

    results = telemetry_coverage(
        session, environment="o5-env", since=SINCE, service_ids=[subject_id]
    )
    assert results[0].http_observed is True
    assert results[0].spans_observed is True


def test_o5_reports_messaging_observed_for_a_sender(driver, session):
    subject_id = ids.service_id("invoice-service")
    _persist(
        driver,
        _fact(
            subject_id=subject_id,
            relation_type="RECEIVES_FROM",
            object_id=ids.queue_id("invoice-q"),
            environment="o5-env-2",
        ),
    )

    results = telemetry_coverage(
        session, environment="o5-env-2", since=SINCE, service_ids=[subject_id]
    )
    assert results[0].messaging_observed is True
    assert results[0].http_observed is False
    assert results[0].spans_observed is True


def test_o5_reports_no_telemetry_for_a_service_with_no_observations(session):
    subject_id = ids.service_id("invoice-service")
    results = telemetry_coverage(
        session, environment="o5-env-empty", since=SINCE, service_ids=[subject_id]
    )
    assert results[0].http_observed is False
    assert results[0].messaging_observed is False
    assert results[0].spans_observed is False


def test_o5_provider_side_gap_is_pinned(driver, session):
    # Documents/pins a real, inherited limitation: an operation minted for an undeclared provider
    # (Fall B - see operation_resolver.py) never gets a PROVIDES edge, so the "provider" service's
    # http_observed stays False even though real observed traffic targets its operation.
    caller_id = ids.service_id("order-service")
    ghost_provider_id = "service:ghostservice"
    ghost_operation_id = ids.operation_id(ghost_provider_id, "GET", "/ghost")
    _persist(
        driver,
        _fact(
            subject_id=caller_id,
            relation_type="CALLS",
            object_id=ghost_operation_id,
            environment="o5-gap-env",
        ),
        entities=[
            ObservedOnlyEntity(id=ghost_provider_id, label="Service", name="GhostService"),
            ObservedOnlyEntity(id=ghost_operation_id, label="Operation", name="GET /ghost"),
        ],
    )

    results = telemetry_coverage(
        session, environment="o5-gap-env", since=SINCE, service_ids=[ghost_provider_id]
    )
    assert results[0].http_observed is False  # the documented gap, pinned by a real assertion


# --- service_runtime_profile: composes O2+O3+O4+O5 for one service (11G) ------------------------


def test_service_runtime_profile_combines_confirmed_observed_only_and_declared_only(
    driver, session
):
    order_id = ids.service_id("order-service")
    product_operation_id = ids.operation_id(
        ids.service_id("product-service"), "GET", "/products/{id}"
    )
    product_service_id = ids.service_id("product-service")
    legacy_operation_id = ids.operation_id(product_service_id, "GET", "/legacy/pricing")

    # order-service -> product-service GET /products/{id}: declared (examples fixture) + observed -> CONFIRMED
    # order-service -> undeclared operation: observed only -> OBSERVED_ONLY
    # order-service -> payment-q: declared (examples fixture), left unobserved in this env -> NOT_OBSERVED_IN_WINDOW
    _persist(
        driver,
        _fact(
            subject_id=order_id,
            relation_type="CALLS",
            object_id=product_operation_id,
            environment="profile-env",
        ),
        _fact(
            subject_id=order_id,
            relation_type="CALLS",
            object_id=legacy_operation_id,
            environment="profile-env",
        ),
        entities=[
            ObservedOnlyEntity(
                id=legacy_operation_id, label="Operation", name="GET /legacy/pricing"
            )
        ],
    )

    profile = service_runtime_profile(
        session, service_id=order_id, environment="profile-env", since=SINCE
    )
    assert profile is not None
    assert profile.service_id == order_id
    assert profile.environment == "profile-env"

    by_status = {}
    for r in profile.relations:
        by_status.setdefault(r.status, []).append(r)

    assert any(r.target_id == product_service_id for r in by_status.get("CONFIRMED", []))
    assert any(r.target_id == legacy_operation_id for r in by_status.get("OBSERVED_ONLY", []))
    declared_only_targets = {r.target_id for r in by_status.get(NOT_OBSERVED_IN_WINDOW, [])}
    assert ids.queue_id("payment-q") in declared_only_targets

    direct_coverage = telemetry_coverage(
        session, environment="profile-env", since=SINCE, service_ids=[order_id]
    )[0]
    assert profile.coverage.http_observed == direct_coverage.http_observed
    assert profile.coverage.messaging_observed == direct_coverage.messaging_observed


def test_service_runtime_profile_returns_none_for_unknown_service(session):
    profile = service_runtime_profile(
        session, service_id="service:does-not-exist", environment="profile-env", since=SINCE
    )
    assert profile is None
