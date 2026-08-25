from pathlib import Path

import yaml

from app.canonical.ids import operation_id, service_id
from app.canonical.model import ArchitectureModel, Direction

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "example_architecture.yaml"


def load_example_architecture() -> ArchitectureModel:
    data = yaml.safe_load(FIXTURE_PATH.read_text())
    return ArchitectureModel(**data)


def test_example_architecture_validates():
    model = load_example_architecture()
    assert len(model.services) == 4
    assert len(model.operations) == 1
    assert len(model.queues) == 4
    assert len(model.messages) == 2
    assert len(model.schemas) == 3
    assert len(model.provenance) == 5


def test_service_ids_match_id_builder():
    model = load_example_architecture()
    service_ids = {s.id for s in model.services}
    for slug in ("order-service", "product-service", "payment-service", "invoice-service"):
        assert service_id(slug) in service_ids


def test_operation_id_matches_id_builder():
    model = load_example_architecture()
    [operation] = model.operations
    assert operation.id == operation_id("product-service", operation.method, operation.path)


def test_relations_reference_existing_entities():
    model = load_example_architecture()
    known_ids = {
        *(s.id for s in model.services),
        *(o.id for o in model.operations),
        *(q.id for q in model.queues),
        *(m.id for m in model.messages),
        *(sc.id for sc in model.schemas),
    }
    for relation in model.relations:
        assert relation.source_id in known_ids
        assert relation.target_id in known_ids


def test_unused_q_has_sender_but_no_consumer():
    model = load_example_architecture()
    senders = {r.target_id for r in model.relations if r.type == "SENDS"}
    consumers = {r.target_id for r in model.relations if r.type == "RECEIVES_FROM"}
    assert "queue:unused-q" in senders
    assert "queue:unused-q" not in consumers


def test_unknown_producer_q_has_consumer_but_no_sender():
    model = load_example_architecture()
    senders = {r.target_id for r in model.relations if r.type == "SENDS"}
    consumers = {r.target_id for r in model.relations if r.type == "RECEIVES_FROM"}
    assert "queue:unknown-producer-q" in consumers
    assert "queue:unknown-producer-q" not in senders


def test_direction_enum_values():
    assert Direction.SEND == "SEND"
    assert Direction.RECEIVE == "RECEIVE"
