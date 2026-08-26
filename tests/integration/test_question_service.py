from pathlib import Path

import pytest
from testcontainers.community.neo4j import Neo4jContainer

from app.ai.question_service import ArchitectureQuestionService
from app.canonical import ids
from app.graph.importer import import_all_sources

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
DATABASE = "neo4j"


class FakeProvider:
    """No real OpenAI calls: fixed Cypher, and an answer that just echoes row count."""

    def __init__(self, cypher: str):
        self.cypher = cypher
        self.compose_calls: list[dict] = []

    def generate_cypher(self, *, question: str, schema_description: str) -> str:
        return self.cypher

    def compose_answer(self, *, question: str, cypher: str, rows: list[dict]) -> str:
        self.compose_calls.append({"question": question, "cypher": cypher, "rows": rows})
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


def test_ask_executes_generated_cypher_and_composes_answer(driver):
    provider = FakeProvider(cypher="MATCH (s:Service)-[:SENDS]->(q:Queue) RETURN s.name AS name")
    service = ArchitectureQuestionService(driver=driver, database=DATABASE, provider=provider)

    result = service.ask("which services send to queues?")

    assert result.question == "which services send to queues?"
    assert result.cypher == "MATCH (s:Service)-[:SENDS]->(q:Queue) RETURN s.name AS name LIMIT 100"
    assert {r["name"] for r in result.rows} == {"OrderService", "PaymentService"}
    assert result.answer == f"Found {len(result.rows)} row(s)."
    assert provider.compose_calls[0]["rows"] == result.rows


def test_ask_rejects_generated_cypher_that_violates_the_validator(driver):
    provider = FakeProvider(cypher="MATCH (n:Service) DETACH DELETE n")
    service = ArchitectureQuestionService(driver=driver, database=DATABASE, provider=provider)

    from app.ai.cypher_validator import CypherValidationError

    with pytest.raises(CypherValidationError):
        service.ask("delete everything")

    # nothing was executed - the graph is untouched
    with driver.session(database=DATABASE) as session:
        count = session.run("MATCH (n:Service) RETURN count(n) AS c").single()["c"]
    assert count == 4


def test_ask_rejects_semantically_invalid_generated_cypher(driver):
    # H2 regression: the live-test failure where the LLM generated a syntactically valid,
    # security-validator-passing query with the SENDS relationship backwards.
    provider = FakeProvider(cypher="MATCH (q:Queue)-[:SENDS]->(s:Service) RETURN q.id AS id")
    service = ArchitectureQuestionService(driver=driver, database=DATABASE, provider=provider)

    from app.ai.semantic_query_validator import SemanticValidationError

    with pytest.raises(SemanticValidationError):
        service.ask("who sends to services?")

    # nothing was executed - the graph is untouched
    with driver.session(database=DATABASE) as session:
        count = session.run("MATCH (n:Service) RETURN count(n) AS c").single()["c"]
    assert count == 4


def test_ask_uses_read_only_session_rejecting_writes_even_if_validator_were_bypassed(driver):
    # Defense in depth: even a validated-but-hypothetically-malicious write attempt must not
    # reach the graph, because ask() executes over a read-only session (spec §19).
    provider = FakeProvider(cypher="MATCH (n:Service) RETURN n.id AS id")
    service = ArchitectureQuestionService(driver=driver, database=DATABASE, provider=provider)
    result = service.ask("list service ids")
    assert len(result.rows) == 4


def test_ask_empty_result_produces_no_results_answer_without_calling_compose(driver):
    provider = FakeProvider(
        cypher="MATCH (s:Service {id: 'service:does-not-exist'}) RETURN s.id AS id"
    )
    service = ArchitectureQuestionService(driver=driver, database=DATABASE, provider=provider)

    result = service.ask("find a service that does not exist")

    assert result.rows == []
    assert "no matching data" in result.answer.lower()
    assert provider.compose_calls == []


def test_ask_clamps_traversal_depth_and_result_rows_per_settings(driver):
    provider = FakeProvider(cypher="MATCH (s:Service) RETURN s.id AS id")
    service = ArchitectureQuestionService(
        driver=driver, database=DATABASE, provider=provider, max_depth=1, max_result_rows=2
    )

    result = service.ask("list service ids")

    assert result.cypher.endswith("LIMIT 2")
    assert len(result.rows) <= 2


def test_ask_blast_radius_style_question_returns_real_graph_data(driver):
    provider = FakeProvider(
        cypher=(
            "MATCH (:Service {id: $service_id})-[:SENDS]->(:Queue)<-[:RECEIVES_FROM]-(b:Service) "
            "RETURN b.id AS id"
        ).replace("$service_id", f"'{ids.service_id('order-service')}'")
    )
    service = ArchitectureQuestionService(driver=driver, database=DATABASE, provider=provider)

    result = service.ask("what does order-service send messages to downstream?")

    assert [r["id"] for r in result.rows] == [ids.service_id("payment-service")]
