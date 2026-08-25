from collections import defaultdict

from app.canonical.model import ArchitectureModel

SCHEMA_RELATION_TYPES = {"REQUEST_SCHEMA", "RESPONSE_SCHEMA", "CONFORMS_TO"}


class CanonicalValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _check_unique(entity_ids: list[str], label: str, errors: list[str]) -> None:
    seen: set[str] = set()
    for entity_id in entity_ids:
        if entity_id in seen:
            errors.append(f"{label} id is not unique: {entity_id}")
        seen.add(entity_id)


def validate_canonical_model(model: ArchitectureModel) -> None:
    """Enforces V1-V8 (spec §10) against a fully merged ArchitectureModel."""
    errors: list[str] = []

    service_ids = {s.id for s in model.services}
    queue_ids = {q.id for q in model.queues}
    message_ids = {m.id for m in model.messages}
    schema_ids = {s.id for s in model.schemas}
    operation_ids = {o.id for o in model.operations}

    # V1 / V3 / V4: unique stable ids
    _check_unique([s.id for s in model.services], "Service", errors)
    _check_unique([q.id for q in model.queues], "Queue", errors)
    _check_unique([m.id for m in model.messages], "Message", errors)

    # V2: every operation has exactly one provider, matching its own service_id
    provides_sources_by_target: dict[str, list[str]] = defaultdict(list)
    for relation in model.relations:
        if relation.type == "PROVIDES":
            provides_sources_by_target[relation.target_id].append(relation.source_id)
    for operation in model.operations:
        providers = provides_sources_by_target.get(operation.id, [])
        if len(providers) != 1:
            errors.append(
                f"Operation {operation.id} must have exactly one PROVIDES relation, found {len(providers)}"
            )
        elif providers[0] != operation.service_id:
            errors.append(
                f"Operation {operation.id} is provided by {providers[0]} but declares "
                f"service_id {operation.service_id}"
            )

    # V5: every CALLS relation references an existing operation
    for relation in model.relations:
        if relation.type == "CALLS" and relation.target_id not in operation_ids:
            errors.append(
                f"CALLS {relation.source_id} -> {relation.target_id} references unknown operation"
            )

    # V6: schema references point to an existing schema
    for relation in model.relations:
        if relation.type in SCHEMA_RELATION_TYPES and relation.target_id not in schema_ids:
            errors.append(
                f"{relation.type} {relation.source_id} -> {relation.target_id} references unknown schema"
            )
    for operation in model.operations:
        for schema_id in (*operation.request_schema_ids, *operation.response_schema_ids):
            if schema_id not in schema_ids:
                errors.append(f"Operation {operation.id} references unknown schema {schema_id}")
    for message in model.messages:
        if message.schema_id and message.schema_id not in schema_ids:
            errors.append(f"Message {message.id} references unknown schema {message.schema_id}")

    # V7: a DLQ must not point to itself
    for relation in model.relations:
        if relation.type == "DEAD_LETTERS_TO" and relation.source_id == relation.target_id:
            errors.append(f"Queue {relation.source_id} cannot be its own DLQ")

    # V8: relations only reference existing source/target entities
    known_ids = service_ids | operation_ids | queue_ids | message_ids | schema_ids
    for relation in model.relations:
        if relation.source_id not in known_ids:
            errors.append(f"Relation {relation.type} has unknown source {relation.source_id}")
        if relation.target_id not in known_ids:
            errors.append(f"Relation {relation.type} has unknown target {relation.target_id}")

    # Evidence: every relation's evidence_ids must reference a Provenance record in this model
    evidence_ids = {p.id for p in model.provenance}
    for relation in model.relations:
        for evidence_id in relation.evidence_ids:
            if evidence_id not in evidence_ids:
                errors.append(
                    f"Relation {relation.type} {relation.source_id} -> {relation.target_id} "
                    f"references unknown evidence {evidence_id}"
                )

    if errors:
        raise CanonicalValidationError(errors)
