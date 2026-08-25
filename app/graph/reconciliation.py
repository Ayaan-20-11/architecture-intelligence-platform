from dataclasses import dataclass

from app.canonical.model import ArchitectureModel, Relation

KNOWN_RELATION_TYPES = {
    "PROVIDES",
    "CALLS",
    "REQUEST_SCHEMA",
    "RESPONSE_SCHEMA",
    "SENDS",
    "RECEIVES_FROM",
    "CARRIES",
    "CONFORMS_TO",
    "DEAD_LETTERS_TO",
}


def relation_key(relation: Relation) -> str:
    return f"{relation.type}:{relation.source_id}:{relation.target_id}"


def model_node_ids(model: ArchitectureModel) -> set[str]:
    return {
        *(s.id for s in model.services),
        *(o.id for o in model.operations),
        *(q.id for q in model.queues),
        *(m.id for m in model.messages),
        *(sc.id for sc in model.schemas),
    }


def model_relation_keys(model: ArchitectureModel) -> set[str]:
    return {relation_key(r) for r in model.relations}


@dataclass(frozen=True)
class ReconciliationPlan:
    stale_node_ids: frozenset[str]
    stale_relation_keys: frozenset[str]


def plan_reconciliation(
    *, existing_node_ids: set[str], existing_relation_keys: set[str], new_model: ArchitectureModel
) -> ReconciliationPlan:
    """Computes which of a service's previously-tagged facts are no longer present in its new import (spec §12)."""
    return ReconciliationPlan(
        stale_node_ids=frozenset(existing_node_ids - model_node_ids(new_model)),
        stale_relation_keys=frozenset(existing_relation_keys - model_relation_keys(new_model)),
    )
