from pathlib import Path

import pytest
from testcontainers.community.neo4j import Neo4jContainer

from app.canonical.model import (
    ArchitectureModel,
    Message,
    Operation,
    Queue,
    Relation,
    Schema,
    Service,
)
from app.graph.importer import import_all_sources, import_service
from app.graph.schema import ensure_schema
from app.provenance.model import Provenance

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
DATABASE = "neo4j"


@pytest.fixture(scope="module")
def neo4j_container():
    with Neo4jContainer("neo4j:5") as container:
        yield container


@pytest.fixture
def driver(neo4j_container):
    drv = neo4j_container.get_driver()
    yield drv
    drv.close()


@pytest.fixture(autouse=True)
def clean_database(driver):
    with driver.session(database=DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n")
    yield


def _count(driver, query: str, **params) -> int:
    with driver.session(database=DATABASE) as session:
        return session.run(query, **params).single()["c"]


def test_ensure_schema_creates_constraints(driver):
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        names = {
            record["name"] for record in session.run("SHOW CONSTRAINTS YIELD name RETURN name")
        }
    assert {"service_id", "operation_id", "queue_id", "message_id", "schema_id"} <= names


def test_import_service_creates_nodes_and_relations(driver):
    model = ArchitectureModel(
        services=[Service(id="service:product-service", name="ProductService")],
        operations=[
            Operation(
                id="operation:product-service:GET:/products/{id}",
                service_id="service:product-service",
                operation_id="getProduct",
                method="GET",
                path="/products/{id}",
                response_schema_ids=["schema:Product"],
            )
        ],
        schemas=[Schema(id="schema:Product", name="Product", format="application/json")],
        relations=[
            Relation(
                type="PROVIDES",
                source_id="service:product-service",
                target_id="operation:product-service:GET:/products/{id}",
            ),
            Relation(
                type="RESPONSE_SCHEMA",
                source_id="operation:product-service:GET:/products/{id}",
                target_id="schema:Product",
            ),
        ],
    )

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        stats = import_service(session, "product-service", model)

    assert stats.nodes_written == 3
    assert stats.relations_written == 2
    assert stats.nodes_expired == 0
    assert stats.relations_expired == 0

    assert (
        _count(driver, "MATCH (n:Service {id: 'service:product-service'}) RETURN count(n) AS c")
        == 1
    )
    assert _count(driver, "MATCH ()-[r:PROVIDES]->() RETURN count(r) AS c") == 1
    assert _count(driver, "MATCH ()-[r:RESPONSE_SCHEMA]->() RETURN count(r) AS c") == 1

    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (n:Service {id: 'service:product-service'}) RETURN n.sources AS sources"
        ).single()
    assert record["sources"] == ["product-service"]


def test_import_service_creates_evidence_node_and_tags_relation(driver):
    evidence = Provenance(
        id="evidence:openapi:product-service",
        source_type="OPENAPI",
        source_file="product-service/openapi.yaml",
        source_revision="abc123",
    )
    model = ArchitectureModel(
        services=[Service(id="service:product-service", name="ProductService")],
        operations=[
            Operation(
                id="operation:product-service:GET:/products/{id}",
                service_id="service:product-service",
                operation_id="getProduct",
                method="GET",
                path="/products/{id}",
            )
        ],
        relations=[
            Relation(
                type="PROVIDES",
                source_id="service:product-service",
                target_id="operation:product-service:GET:/products/{id}",
                evidence_ids=[evidence.id],
            )
        ],
        provenance=[evidence],
    )
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        stats = import_service(session, "product-service", model)

    assert stats.nodes_written == 3  # service + operation + evidence

    with driver.session(database=DATABASE) as session:
        evidence_record = session.run(
            "MATCH (e:Evidence {id: $id}) RETURN e.source_type AS source_type, "
            "e.source_file AS source_file, e.source_revision AS source_revision, "
            "e.evidence_type AS evidence_type, e.sources AS sources",
            id=evidence.id,
        ).single()
    assert evidence_record["source_type"] == "OPENAPI"
    assert evidence_record["source_file"] == "product-service/openapi.yaml"
    assert evidence_record["source_revision"] == "abc123"
    assert evidence_record["evidence_type"] == "DECLARED"
    assert evidence_record["sources"] == ["product-service"]

    with driver.session(database=DATABASE) as session:
        relation_record = session.run(
            "MATCH ()-[r:PROVIDES]->() RETURN r.evidence_ids AS evidence_ids"
        ).single()
    assert relation_record["evidence_ids"] == [evidence.id]


def test_shared_relation_accumulates_evidence_from_both_declaring_services(driver):
    # Mirrors the real fixture landscape: order-service (sender) and payment-service
    # (receiver) both independently declare CARRIES payment-q -> PaymentRequested in
    # their own AsyncAPI docs - the same relation triple, two separate import
    # transactions, two separate pieces of evidence that must both survive.
    evidence_order = Provenance(
        id="evidence:asyncapi:order-service",
        source_type="ASYNCAPI",
        source_file="order-service/asyncapi.yaml",
    )
    evidence_payment = Provenance(
        id="evidence:asyncapi:payment-service",
        source_type="ASYNCAPI",
        source_file="payment-service/asyncapi.yaml",
    )
    order_model = ArchitectureModel(
        services=[Service(id="service:order-service", name="OrderService")],
        queues=[Queue(id="queue:payment-q", name="payment-q")],
        messages=[Message(id="message:PaymentRequested:v2", name="PaymentRequested", version="v2")],
        relations=[
            Relation(
                type="SENDS",
                source_id="service:order-service",
                target_id="queue:payment-q",
                evidence_ids=[evidence_order.id],
            ),
            Relation(
                type="CARRIES",
                source_id="queue:payment-q",
                target_id="message:PaymentRequested:v2",
                evidence_ids=[evidence_order.id],
            ),
        ],
        provenance=[evidence_order],
    )
    payment_model = ArchitectureModel(
        services=[Service(id="service:payment-service", name="PaymentService")],
        queues=[Queue(id="queue:payment-q", name="payment-q")],
        messages=[Message(id="message:PaymentRequested:v2", name="PaymentRequested", version="v2")],
        relations=[
            Relation(
                type="RECEIVES_FROM",
                source_id="service:payment-service",
                target_id="queue:payment-q",
                evidence_ids=[evidence_payment.id],
            ),
            Relation(
                type="CARRIES",
                source_id="queue:payment-q",
                target_id="message:PaymentRequested:v2",
                evidence_ids=[evidence_payment.id],
            ),
        ],
        provenance=[evidence_payment],
    )

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        import_service(session, "order-service", order_model)
        import_service(session, "payment-service", payment_model)

    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (:Queue {id:'queue:payment-q'})-[r:CARRIES]->(:Message) "
            "RETURN r.evidence_ids AS evidence_ids"
        ).single()
    assert set(record["evidence_ids"]) == {evidence_order.id, evidence_payment.id}

    # order-service stops declaring payment-q entirely (e.g. its asyncapi.yaml was removed)
    order_model_without_payment_q = ArchitectureModel(
        services=[Service(id="service:order-service", name="OrderService")]
    )
    with driver.session(database=DATABASE) as session:
        import_service(session, "order-service", order_model_without_payment_q)

    # order-service's evidence is gone entirely (no longer referenced by anyone)
    assert (
        _count(driver, "MATCH (e:Evidence {id: $id}) RETURN count(e) AS c", id=evidence_order.id)
        == 0
    )
    # the CARRIES relation survives (payment-service still declares it) with only
    # payment-service's evidence remaining
    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (:Queue {id:'queue:payment-q'})-[r:CARRIES]->(:Message) "
            "RETURN r.evidence_ids AS evidence_ids"
        ).single()
    assert record["evidence_ids"] == [evidence_payment.id]


def test_import_service_is_idempotent(driver):
    model = ArchitectureModel(
        services=[Service(id="service:x", name="X")],
        queues=[Queue(id="queue:x-q", name="x-q")],
        relations=[Relation(type="SENDS", source_id="service:x", target_id="queue:x-q")],
    )
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        import_service(session, "x", model)
        import_service(session, "x", model)

    assert _count(driver, "MATCH (n) RETURN count(n) AS c") == 2
    assert _count(driver, "MATCH ()-[r]->() RETURN count(r) AS c") == 1


def test_reimport_expires_stale_facts_no_longer_declared(driver):
    with_queue = ArchitectureModel(
        services=[Service(id="service:x", name="X")],
        queues=[Queue(id="queue:old-q", name="old-q")],
        relations=[Relation(type="SENDS", source_id="service:x", target_id="queue:old-q")],
    )
    without_queue = ArchitectureModel(
        services=[Service(id="service:x", name="X")],
        queues=[Queue(id="queue:new-q", name="new-q")],
        relations=[Relation(type="SENDS", source_id="service:x", target_id="queue:new-q")],
    )

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        import_service(session, "x", with_queue)
        assert _count(driver, "MATCH (q:Queue {id: 'queue:old-q'}) RETURN count(q) AS c") == 1

        stats = import_service(session, "x", without_queue)

    assert stats.nodes_expired == 1
    assert stats.relations_expired == 1
    assert _count(driver, "MATCH (q:Queue {id: 'queue:old-q'}) RETURN count(q) AS c") == 0
    assert _count(driver, "MATCH (q:Queue {id: 'queue:new-q'}) RETURN count(q) AS c") == 1


def test_shared_queue_kept_when_still_referenced_by_another_service(driver):
    sender_model = ArchitectureModel(
        services=[Service(id="service:sender", name="Sender")],
        queues=[Queue(id="queue:shared-q", name="shared-q")],
        relations=[Relation(type="SENDS", source_id="service:sender", target_id="queue:shared-q")],
    )
    receiver_model = ArchitectureModel(
        services=[Service(id="service:receiver", name="Receiver")],
        queues=[Queue(id="queue:shared-q", name="shared-q")],
        relations=[
            Relation(type="RECEIVES_FROM", source_id="service:receiver", target_id="queue:shared-q")
        ],
    )
    sender_model_without_queue = ArchitectureModel(
        services=[Service(id="service:sender", name="Sender")]
    )

    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        import_service(session, "sender", sender_model)
        import_service(session, "receiver", receiver_model)

        with driver.session(database=DATABASE) as read_session:
            sources = read_session.run(
                "MATCH (q:Queue {id: 'queue:shared-q'}) RETURN q.sources AS sources"
            ).single()["sources"]
        assert set(sources) == {"sender", "receiver"}

        # sender no longer declares the queue, but receiver still does -> queue must survive
        import_service(session, "sender", sender_model_without_queue)

    assert _count(driver, "MATCH (q:Queue {id: 'queue:shared-q'}) RETURN count(q) AS c") == 1
    with driver.session(database=DATABASE) as session:
        sources = session.run(
            "MATCH (q:Queue {id: 'queue:shared-q'}) RETURN q.sources AS sources"
        ).single()["sources"]
    assert sources == ["receiver"]


def test_import_service_rejects_unknown_relation_type_without_writing_anything(driver):
    model = ArchitectureModel(
        services=[Service(id="service:x", name="X")],
        relations=[Relation(type="BOGUS", source_id="service:x", target_id="service:x")],
    )
    with driver.session(database=DATABASE) as session:
        ensure_schema(session)
        with pytest.raises(ValueError, match="Unknown relation type"):
            import_service(session, "x", model)

    assert _count(driver, "MATCH (n) RETURN count(n) AS c") == 0


def test_import_all_sources_real_examples_end_to_end(driver):
    stats = import_all_sources(driver, database=DATABASE, root=EXAMPLES_DIR)

    assert set(stats.keys()) == {
        "order-service",
        "product-service",
        "payment-service",
        "invoice-service",
    }
    assert _count(driver, "MATCH (n:Service) RETURN count(n) AS c") == 4

    calls = _count(driver, "MATCH ()-[r:CALLS]->() RETURN count(r) AS c")
    assert calls == 1
    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (s:Service {id: 'service:order-service'})-[:CALLS]->(o:Operation) RETURN o.id AS id"
        ).single()
    assert record["id"] == "operation:product-service:GET:/products/{id}"

    assert _count(driver, "MATCH ()-[r:DEAD_LETTERS_TO]->() RETURN count(r) AS c") == 1
    assert _count(driver, "MATCH (q:Queue) RETURN count(q) AS c") == 5

    # Evidence: one per scanned source file - order-service has 3 (openapi/asyncapi/manifest),
    # product-service/payment-service/invoice-service have 1 each (AC13).
    assert _count(driver, "MATCH (e:Evidence) RETURN count(e) AS c") == 6

    # the manifest-derived CALLS relation is backed by exactly the manifest's evidence
    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (s:Service {id: 'service:order-service'})-[r:CALLS]->(:Operation) "
            "RETURN r.evidence_ids AS evidence_ids"
        ).single()
    assert record["evidence_ids"] == ["evidence:manifest:order-service"]

    # payment-q CARRIES PaymentRequested is independently declared by order-service
    # (sender) and payment-service (receiver) - both pieces of evidence must be present
    with driver.session(database=DATABASE) as session:
        record = session.run(
            "MATCH (:Queue {id: 'queue:payment-q'})-[r:CARRIES]->(:Message) "
            "RETURN r.evidence_ids AS evidence_ids"
        ).single()
    assert set(record["evidence_ids"]) == {
        "evidence:asyncapi:order-service",
        "evidence:asyncapi:payment-service",
    }


def test_import_all_sources_is_idempotent(driver):
    import_all_sources(driver, database=DATABASE, root=EXAMPLES_DIR)
    first_nodes = _count(driver, "MATCH (n) RETURN count(n) AS c")
    first_relations = _count(driver, "MATCH ()-[r]->() RETURN count(r) AS c")

    import_all_sources(driver, database=DATABASE, root=EXAMPLES_DIR)
    second_nodes = _count(driver, "MATCH (n) RETURN count(n) AS c")
    second_relations = _count(driver, "MATCH ()-[r]->() RETURN count(r) AS c")

    assert first_nodes == second_nodes
    assert first_relations == second_relations
