from datetime import UTC, datetime
from pathlib import Path

import pytest
from testcontainers.community.neo4j import Neo4jContainer

from app.canonical import ids
from app.graph.importer import import_all_sources
from app.provenance.model import ObservedEvidence
from app.telemetry.aggregator import persist_observation_batch
from app.telemetry.model import ObservationBatch, ObservedFactCandidate, ObservedOnlyEntity

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
DATABASE = "neo4j"


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


def _fact(*, environment: str = "production", **overrides) -> ObservedFactCandidate:
    # environment is part of the deterministic evidence id (subject/relation/object/day/environment)
    # - tests that must not share an evidence bucket with each other (the module-scoped graph
    # fixture is shared across this whole file) pass a distinct environment to stay isolated.
    subject_id = ids.service_id("order-service")
    relation_type = "CALLS"
    object_id = ids.operation_id(ids.service_id("product-service"), "GET", "/products/{id}")
    bucket_start = datetime(2026, 8, 26, tzinfo=UTC)
    bucket_end = datetime(2026, 8, 27, tzinfo=UTC)
    timestamp = overrides.pop("timestamp", datetime(2026, 8, 26, 12, 0, tzinfo=UTC))
    trace_id = overrides.pop("trace_id", "a" * 32)

    evidence = ObservedEvidence(
        id=ids.observed_evidence_id(
            environment, bucket_start, subject_id, relation_type, object_id
        ),
        environment=environment,
        bucket_start=bucket_start,
        bucket_end=bucket_end,
        first_seen=timestamp,
        last_seen=timestamp,
        observation_count=1,
        sample_trace_ids=[trace_id],
        service_version="1.0.0",
    )
    defaults = {
        "subject_id": subject_id,
        "relation_type": relation_type,
        "object_id": object_id,
        "environment": environment,
        "timestamp": timestamp,
        "trace_id": trace_id,
        "source_service_version": "1.0.0",
        "evidence": evidence,
    }
    defaults.update(overrides)
    return ObservedFactCandidate(**defaults)


def _relation_evidence_ids(session, subject_id: str, object_id: str) -> list[str]:
    record = session.run(
        "MATCH (a {id: $subject_id})-[r:CALLS]->(b {id: $object_id}) RETURN r.evidence_ids AS ids",
        subject_id=subject_id,
        object_id=object_id,
    ).single()
    return record["ids"] if record else []


def test_observed_only_entity_creates_a_stub_node(driver, session):
    entity = ObservedOnlyEntity(id="service:fraudservice", label="Service", name="FraudService")
    persist_observation_batch(driver, DATABASE, ObservationBatch(entities=[entity]))

    record = session.run(
        "MATCH (s:Service {id: $id}) RETURN s.name AS name, s.discovery_status AS discovery_status",
        id="service:fraudservice",
    ).single()
    assert record["name"] == "FraudService"
    assert record["discovery_status"] == "OBSERVED_ONLY"


def test_reobserving_the_same_entity_does_not_clobber_it(driver, session):
    entity = ObservedOnlyEntity(id="service:fraudservice", label="Service", name="FraudService")
    persist_observation_batch(driver, DATABASE, ObservationBatch(entities=[entity]))
    persist_observation_batch(driver, DATABASE, ObservationBatch(entities=[entity]))

    count = session.run(
        "MATCH (s:Service {id: $id}) RETURN count(s) AS c", id="service:fraudservice"
    ).single()["c"]
    assert count == 1


def test_declared_node_is_never_touched_by_a_stub_merge(driver, session):
    # order-service already exists as a real declared node - MERGE ... ON CREATE SET must not fire.
    entity = ObservedOnlyEntity(
        id=ids.service_id("order-service"), label="Service", name="should-not-be-written"
    )
    persist_observation_batch(driver, DATABASE, ObservationBatch(entities=[entity]))

    record = session.run(
        "MATCH (s:Service {id: $id}) RETURN s.name AS name, s.discovery_status AS discovery_status",
        id=ids.service_id("order-service"),
    ).single()
    assert record["name"] == "OrderService"
    assert record["discovery_status"] is None


def test_observed_fact_adds_evidence_alongside_the_existing_declared_evidence(driver, session):
    subject_id = ids.service_id("order-service")
    object_id = ids.operation_id(ids.service_id("product-service"), "GET", "/products/{id}")
    declared_evidence_ids = _relation_evidence_ids(session, subject_id, object_id)
    assert declared_evidence_ids, "fixture must already declare this CALLS relation with evidence"

    fact = _fact()
    persist_observation_batch(driver, DATABASE, ObservationBatch(facts=[fact]))

    evidence_ids = _relation_evidence_ids(session, subject_id, object_id)
    assert set(declared_evidence_ids) <= set(evidence_ids)
    assert fact.evidence.id in evidence_ids

    evidence_record = session.run(
        "MATCH (e:Evidence {id: $id}) RETURN e.source_type AS source_type, "
        "e.evidence_type AS evidence_type",
        id=fact.evidence.id,
    ).single()
    assert evidence_record["source_type"] == "OPENTELEMETRY"
    assert evidence_record["evidence_type"] == "OBSERVED"


def test_persisting_the_same_fact_twice_merges_the_evidence_bucket(driver, session):
    first = _fact(
        environment="staging", trace_id="1" * 32, timestamp=datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    )
    second = _fact(
        environment="staging", trace_id="2" * 32, timestamp=datetime(2026, 8, 26, 18, 0, tzinfo=UTC)
    )
    assert first.evidence.id == second.evidence.id  # same fact, same day, same environment

    persist_observation_batch(driver, DATABASE, ObservationBatch(facts=[first]))
    persist_observation_batch(driver, DATABASE, ObservationBatch(facts=[second]))

    record = session.run(
        "MATCH (e:Evidence {id: $id}) RETURN e.observation_count AS observation_count, "
        "e.sample_trace_ids AS sample_trace_ids, e.first_seen AS first_seen, e.last_seen AS last_seen",
        id=first.evidence.id,
    ).single()
    assert record["observation_count"] == 2
    assert set(record["sample_trace_ids"]) == {"1" * 32, "2" * 32}
    assert record["first_seen"].to_native() == datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    assert record["last_seen"].to_native() == datetime(2026, 8, 26, 18, 0, tzinfo=UTC)
