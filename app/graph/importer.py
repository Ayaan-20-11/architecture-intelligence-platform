from dataclasses import dataclass
from pathlib import Path

import neo4j

from app.canonical.model import ArchitectureModel
from app.graph.reconciliation import KNOWN_RELATION_TYPES, plan_reconciliation, relation_key
from app.graph.repository import open_session
from app.graph.schema import ensure_schema
from app.ingestion.pipeline import merge_models, parse_sources
from app.validation.canonical_validation import validate_canonical_model

NODE_LABELS = {
    "services": "Service",
    "operations": "Operation",
    "queues": "Queue",
    "messages": "Message",
    "schemas": "Schema",
    "provenance": "Evidence",
}

_MERGE_NODE_TEMPLATE = (
    "MERGE (n:{label} {{id: $id}}) "
    "SET n += $props "
    "SET n.sources = CASE WHEN $service_id IN coalesce(n.sources, []) "
    "THEN n.sources ELSE coalesce(n.sources, []) + $service_id END"
)

_MERGE_RELATION_TEMPLATE = (
    "MATCH (a {{id: $source_id}}), (b {{id: $target_id}}) "
    "MERGE (a)-[r:{relation_type}]->(b) "
    "SET r.key = $key "
    "SET r.sources = CASE WHEN $service_id IN coalesce(r.sources, []) "
    "THEN r.sources ELSE coalesce(r.sources, []) + $service_id END "
    "SET r.evidence_ids = reduce(acc = coalesce(r.evidence_ids, []), eid IN $evidence_ids | "
    "CASE WHEN eid IN acc THEN acc ELSE acc + eid END)"
)

_EXISTING_NODE_IDS_QUERY = (
    "MATCH (n) WHERE $service_id IN coalesce(n.sources, []) RETURN n.id AS id"
)
_EXISTING_RELATION_KEYS_QUERY = (
    "MATCH ()-[r]->() WHERE $service_id IN coalesce(r.sources, []) RETURN r.key AS key"
)

_STRIP_STALE_EVIDENCE_QUERY = (
    "UNWIND $ids AS eid "
    "MATCH ()-[r]->() WHERE eid IN coalesce(r.evidence_ids, []) "
    "SET r.evidence_ids = [x IN r.evidence_ids WHERE x <> eid]"
)
_EXPIRE_NODES_QUERY = (
    "UNWIND $ids AS nid "
    "MATCH (n {id: nid}) "
    "SET n.sources = [x IN n.sources WHERE x <> $service_id] "
    "WITH n WHERE size(n.sources) = 0 "
    "DETACH DELETE n"
)
# A stale relation key must not be deleted outright just because its declaring service stopped
# declaring it (11H R1/spec Delete(F) iff Evidence(F) = empty) - it may still carry OBSERVED
# evidence (from the H4 telemetry pipeline) or DECLARED evidence from another declaring service
# (spec §5.3's shared-evidence case). So this strips $service_id from r.sources as before, but
# also recomputes r.evidence_ids by removing only the ids that are (a) DECLARED and (b) actually
# attributed to $service_id via that specific Evidence node's own sources array - never touching
# another service's DECLARED evidence or any OBSERVED evidence - and only deletes the relation
# once evidence_ids is truly empty. The list comprehension (not UNWIND+collect) is deliberate:
# UNWIND over an empty evidence_ids list would produce zero rows and silently drop r from the rest
# of the pipeline, which would incorrectly let an evidence-less stale relation survive forever.
_EXPIRE_RELATIONS_QUERY = (
    "UNWIND $keys AS rkey "
    "MATCH ()-[r {key: rkey}]->() "
    "SET r.sources = [x IN r.sources WHERE x <> $service_id] "
    "WITH r, [eid IN r.evidence_ids WHERE NOT EXISTS { "
    "MATCH (e:Evidence {id: eid}) "
    "WHERE e.evidence_type = 'DECLARED' AND $service_id IN coalesce(e.sources, []) "
    "} ] AS remaining_evidence_ids "
    "SET r.evidence_ids = remaining_evidence_ids "
    "WITH r WHERE size(r.evidence_ids) = 0 "
    "DELETE r"
)


@dataclass(frozen=True)
class ImportStats:
    service_id: str
    nodes_written: int
    relations_written: int
    nodes_expired: int
    relations_expired: int


def _write_nodes(tx: neo4j.ManagedTransaction, service_id: str, model: ArchitectureModel) -> int:
    count = 0
    for field_name, label in NODE_LABELS.items():
        query = _MERGE_NODE_TEMPLATE.format(label=label)
        for entity in getattr(model, field_name):
            tx.run(
                query, id=entity.id, props=entity.model_dump(exclude={"id"}), service_id=service_id
            )
            count += 1
    return count


def _write_relations(
    tx: neo4j.ManagedTransaction, service_id: str, model: ArchitectureModel
) -> int:
    for relation in model.relations:
        query = _MERGE_RELATION_TEMPLATE.format(relation_type=relation.type)
        tx.run(
            query,
            source_id=relation.source_id,
            target_id=relation.target_id,
            key=relation_key(relation),
            service_id=service_id,
            evidence_ids=relation.evidence_ids,
        )
    return len(model.relations)


def _import_service_tx(
    tx: neo4j.ManagedTransaction, service_id: str, model: ArchitectureModel
) -> ImportStats:
    for relation in model.relations:
        if relation.type not in KNOWN_RELATION_TYPES:
            raise ValueError(f"Unknown relation type: {relation.type}")

    existing_node_ids = {
        record["id"] for record in tx.run(_EXISTING_NODE_IDS_QUERY, service_id=service_id)
    }
    existing_relation_keys = {
        record["key"] for record in tx.run(_EXISTING_RELATION_KEYS_QUERY, service_id=service_id)
    }
    plan = plan_reconciliation(
        existing_node_ids=existing_node_ids,
        existing_relation_keys=existing_relation_keys,
        new_model=model,
    )

    nodes_written = _write_nodes(tx, service_id, model)
    relations_written = _write_relations(tx, service_id, model)

    if plan.stale_relation_keys:
        tx.run(_EXPIRE_RELATIONS_QUERY, keys=list(plan.stale_relation_keys), service_id=service_id)
    if plan.stale_node_ids:
        tx.run(_STRIP_STALE_EVIDENCE_QUERY, ids=list(plan.stale_node_ids))
        tx.run(_EXPIRE_NODES_QUERY, ids=list(plan.stale_node_ids), service_id=service_id)

    return ImportStats(
        service_id=service_id,
        nodes_written=nodes_written,
        relations_written=relations_written,
        nodes_expired=len(plan.stale_node_ids),
        relations_expired=len(plan.stale_relation_keys),
    )


def import_service(
    session: neo4j.Session, service_id: str, model: ArchitectureModel
) -> ImportStats:
    """Transactionally MERGEs one service's facts and expires its stale ones (spec §12)."""
    return session.execute_write(_import_service_tx, service_id, model)


def import_all_sources(
    driver: neo4j.Driver, *, database: str, root: Path
) -> dict[str, ImportStats]:
    """Runs the pipeline then writes every service to Neo4j, pre-merging all nodes first so cross-service relations always find their target regardless of processing order (spec §5.2/§12.2)."""
    by_service = parse_sources(root)
    validate_canonical_model(merge_models(list(by_service.values())))

    with open_session(driver, database=database) as session:
        ensure_schema(session)
        for service_id, model in by_service.items():
            session.execute_write(_write_nodes, service_id, model)

        return {
            service_id: import_service(session, service_id, model)
            for service_id, model in by_service.items()
        }
