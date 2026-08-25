from app.canonical.model import ArchitectureModel, Queue, Relation, Service
from app.graph.reconciliation import (
    model_node_ids,
    model_relation_keys,
    plan_reconciliation,
    relation_key,
)
from app.provenance.model import Provenance


def test_relation_key_format():
    relation = Relation(type="SENDS", source_id="service:a", target_id="queue:b")
    assert relation_key(relation) == "SENDS:service:a:queue:b"


def test_model_node_ids_collects_all_entity_types():
    model = ArchitectureModel(
        services=[Service(id="service:a", name="A")],
        queues=[Queue(id="queue:b", name="b")],
    )
    assert model_node_ids(model) == {"service:a", "queue:b"}


def test_model_node_ids_includes_evidence():
    model = ArchitectureModel(
        services=[Service(id="service:a", name="A")],
        provenance=[
            Provenance(id="evidence:asyncapi:a", source_type="ASYNCAPI", source_file="a.yaml")
        ],
    )
    assert model_node_ids(model) == {"service:a", "evidence:asyncapi:a"}


def test_model_relation_keys():
    model = ArchitectureModel(
        relations=[Relation(type="SENDS", source_id="service:a", target_id="queue:b")]
    )
    assert model_relation_keys(model) == {"SENDS:service:a:queue:b"}


def test_plan_reconciliation_no_change_yields_no_stale_facts():
    model = ArchitectureModel(
        services=[Service(id="service:a", name="A")],
        relations=[Relation(type="SENDS", source_id="service:a", target_id="queue:b")],
    )
    plan = plan_reconciliation(
        existing_node_ids={"service:a"},
        existing_relation_keys={"SENDS:service:a:queue:b"},
        new_model=model,
    )
    assert plan.stale_node_ids == frozenset()
    assert plan.stale_relation_keys == frozenset()


def test_plan_reconciliation_detects_removed_facts():
    model = ArchitectureModel(services=[Service(id="service:a", name="A")])
    plan = plan_reconciliation(
        existing_node_ids={"service:a", "queue:removed"},
        existing_relation_keys={"SENDS:service:a:queue:removed"},
        new_model=model,
    )
    assert plan.stale_node_ids == frozenset({"queue:removed"})
    assert plan.stale_relation_keys == frozenset({"SENDS:service:a:queue:removed"})


def test_plan_reconciliation_new_facts_are_not_stale():
    model = ArchitectureModel(services=[Service(id="service:a", name="A")])
    plan = plan_reconciliation(
        existing_node_ids=set(), existing_relation_keys=set(), new_model=model
    )
    assert plan.stale_node_ids == frozenset()
    assert plan.stale_relation_keys == frozenset()
