from pathlib import Path

import pytest
from testcontainers.community.neo4j import Neo4jContainer

from app.analysis.blast_radius import blast_radius
from app.analysis.queues import consumers_of_queue, queues_without_senders, senders_of_queue
from app.answer_router import LLMNotConfiguredError, answer_question
from app.canonical import ids
from app.graph.importer import import_all_sources

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
DATABASE = "neo4j"


class ExplodingProvider:
    """A provider whose generate_cypher must never be called for a deterministic question."""

    def generate_cypher(self, *, question: str, schema_description: str) -> str:
        raise AssertionError("generate_cypher must not be called for a deterministic intent")

    def compose_answer(self, *, question: str, cypher: str, rows: list[dict]) -> str:
        raise AssertionError("compose_answer must not be called for a deterministic intent")


class FakeProvider:
    def __init__(self, cypher: str = "MATCH (s:Service) RETURN s.name AS name"):
        self.cypher = cypher

    def generate_cypher(self, *, question: str, schema_description: str) -> str:
        return self.cypher

    def compose_answer(self, *, question: str, cypher: str, rows: list[dict]) -> str:
        return f"Found {len(rows)} row(s)."


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


def _build_question_service(driver, provider):
    from app.ai.question_service import ArchitectureQuestionService

    return ArchitectureQuestionService(driver=driver, database=DATABASE, provider=provider)


# --- deterministic routing for each of the 5 intents -----------------------------------------


def test_a1_queue_senders_routed_deterministically(session, driver):
    routed = answer_question(
        session=session,
        question="Who sends to payment-q?",
        deterministic_threshold=0.9,
        question_service=_build_question_service(driver, ExplodingProvider()),
    )
    assert routed.execution_mode == "DETERMINISTIC"
    assert routed.intent == "A1_QUEUE_SENDERS"
    assert routed.cypher is None
    expected = senders_of_queue(session, ids.queue_id("payment-q"))
    assert routed.rows == [{"id": r.id, "name": r.name} for r in expected]


def test_a2_queue_consumers_routed_deterministically_german(session, driver):
    routed = answer_question(
        session=session,
        question="Wer konsumiert von payment-q?",
        deterministic_threshold=0.9,
        question_service=_build_question_service(driver, ExplodingProvider()),
    )
    assert routed.execution_mode == "DETERMINISTIC"
    assert routed.intent == "A2_QUEUE_CONSUMERS"
    expected = consumers_of_queue(session, ids.queue_id("payment-q"))
    assert routed.rows == [{"id": r.id, "name": r.name} for r in expected]


def test_a3_queues_without_consumers_routed_deterministically(session, driver):
    routed = answer_question(
        session=session,
        question="Which queues have no consumer?",
        deterministic_threshold=0.9,
        question_service=_build_question_service(driver, ExplodingProvider()),
    )
    assert routed.execution_mode == "DETERMINISTIC"
    assert routed.intent == "A3_QUEUES_WITHOUT_CONSUMERS"
    assert routed.rows == [{"id": ids.queue_id("unused-q"), "name": "unused-q"}]


def test_a5_blast_radius_routed_deterministically(session, driver):
    routed = answer_question(
        session=session,
        question="What depends on OrderService?",
        deterministic_threshold=0.9,
        question_service=_build_question_service(driver, ExplodingProvider()),
    )
    assert routed.execution_mode == "DETERMINISTIC"
    assert routed.intent == "A5_BLAST_RADIUS"
    expected = blast_radius(session, ids.service_id("order-service"))
    assert len(routed.rows) == len(expected)


# --- AC-H3-7: the exact Iteration 9 live-test regression --------------------------------------


def test_ac_h3_7_live_test_regression(session, driver):
    routed = answer_question(
        session=session,
        question="What queues have a consumer but no known sender?",
        deterministic_threshold=0.9,
        question_service=_build_question_service(driver, ExplodingProvider()),
    )
    assert routed.execution_mode == "DETERMINISTIC"
    assert routed.intent == "A4_QUEUES_WITHOUT_SENDERS"
    assert [row["queue_name"] for row in routed.rows] == ["unknown-producer-q"]

    expected = queues_without_senders(session)
    assert [r.queue_name for r in expected] == ["unknown-producer-q"]


# --- fallback / negative cases -------------------------------------------------------------------


def test_ambiguous_question_falls_back_to_llm(session, driver):
    provider = FakeProvider(cypher="MATCH (s:Service) RETURN s.name AS name")
    routed = answer_question(
        session=session,
        question="Who sends to payment?",  # ambiguous: payment-q vs payment-dlq
        deterministic_threshold=0.9,
        question_service=_build_question_service(driver, provider),
    )
    assert routed.execution_mode == "LLM"
    assert routed.intent is None
    assert routed.cypher == "MATCH (s:Service) RETURN s.name AS name LIMIT 100"


def test_unknown_question_with_no_provider_raises_llm_not_configured(session):
    with pytest.raises(LLMNotConfiguredError):
        answer_question(
            session=session,
            question="What is the meaning of life?",
            deterministic_threshold=0.9,
            question_service=None,
        )


def test_deterministic_question_never_needs_a_provider(session):
    # No question_service at all - proves the deterministic path is fully independent of the LLM.
    routed = answer_question(
        session=session,
        question="Which queues have no consumer?",
        deterministic_threshold=0.9,
        question_service=None,
    )
    assert routed.execution_mode == "DETERMINISTIC"
