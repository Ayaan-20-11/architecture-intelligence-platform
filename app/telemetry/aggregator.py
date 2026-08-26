import neo4j

from app.graph.reconciliation import KNOWN_RELATION_TYPES
from app.graph.repository import open_session
from app.graph.schema import ensure_schema
from app.provenance.model import ObservedEvidence
from app.telemetry.model import ObservationBatch, ObservedFactCandidate

_MERGE_STUB_NODE_QUERY = (
    "MERGE (n:{label} {{id: $id}}) "
    "ON CREATE SET n.name = $name, n.discovery_status = $discovery_status"
)

_READ_EVIDENCE_QUERY = (
    "MATCH (e:Evidence {id: $id}) "
    "RETURN e.id AS id, e.source_type AS source_type, e.source_file AS source_file, "
    "e.source_revision AS source_revision, e.evidence_type AS evidence_type, "
    "e.environment AS environment, e.bucket_start AS bucket_start, e.bucket_end AS bucket_end, "
    "e.first_seen AS first_seen, e.last_seen AS last_seen, "
    "e.observation_count AS observation_count, e.sample_trace_ids AS sample_trace_ids, "
    "e.service_version AS service_version, e.correlation_mode AS correlation_mode"
)

# 11H R3/spec §14 - "preserve the strongest mode" when merging two evidence buckets. None (no
# mode recorded, e.g. pre-11H-C evidence) is weakest, so any real mode always wins over it.
_CORRELATION_MODE_STRENGTH = {
    None: 0,
    "MESSAGING_SEND": 1,
    "MESSAGING_RECEIVE": 1,
    "MESSAGING_PROCESS": 1,
    "SERVER_ONLY": 2,
    "CLIENT_ONLY": 2,
    "CLIENT_SERVER": 3,
}


def _stronger_mode(a: str | None, b: str | None) -> str | None:
    return a if _CORRELATION_MODE_STRENGTH.get(a, 0) >= _CORRELATION_MODE_STRENGTH.get(b, 0) else b


_MERGE_EVIDENCE_QUERY = "MERGE (e:Evidence {id: $id}) SET e += $props"

# Mirrors app/graph/importer.py's _MERGE_RELATION_TEMPLATE's evidence_ids dedup-append expression,
# but deliberately never touches r.sources - that's declared-import-only reconciliation bookkeeping
# that must not apply to incremental runtime observation (spec §40: absence of observation is not
# evidence of absence, so an observed fact is never "expired" by a later batch not re-observing it).
_MERGE_FACT_RELATION_QUERY = (
    "MATCH (a {{id: $subject_id}}), (b {{id: $object_id}}) "
    "MERGE (a)-[r:{relation_type}]->(b) "
    "SET r.evidence_ids = reduce(acc = coalesce(r.evidence_ids, []), eid IN [$evidence_id] | "
    "CASE WHEN eid IN acc THEN acc ELSE acc + eid END)"
)

_DATETIME_FIELDS = ("bucket_start", "bucket_end", "first_seen", "last_seen")


def _cap_trace_ids(existing: list[str], new: list[str], limit: int = 5) -> list[str]:
    combined = list(existing)
    for trace_id in new:
        if trace_id not in combined:
            combined.append(trace_id)
    return combined[:limit]


def merge_evidence(existing: ObservedEvidence | None, seed: ObservedEvidence) -> ObservedEvidence:
    """Merges a single-observation seed into the existing persisted evidence bucket, if any (spec
    §36). bucket_start/bucket_end are left untouched (taken from the seed) - observed_evidence_id()
    is deterministic per (fact, day, environment), so existing and seed always share the same day
    boundaries by construction whenever both are present."""
    if existing is None:
        return seed
    return seed.model_copy(
        update={
            "first_seen": min(existing.first_seen, seed.first_seen),
            "last_seen": max(existing.last_seen, seed.last_seen),
            "observation_count": existing.observation_count + seed.observation_count,
            "sample_trace_ids": _cap_trace_ids(existing.sample_trace_ids, seed.sample_trace_ids),
            "correlation_mode": _stronger_mode(existing.correlation_mode, seed.correlation_mode),
        }
    )


def _read_existing_evidence(
    tx: neo4j.ManagedTransaction, evidence_id: str
) -> ObservedEvidence | None:
    record = tx.run(_READ_EVIDENCE_QUERY, id=evidence_id).single()
    if record is None:
        return None
    data = dict(record)
    for field in _DATETIME_FIELDS:
        # Neo4j returns temporal properties as neo4j.time.DateTime, not datetime.datetime - Pydantic
        # rejects it outright without this conversion. Read-direction only; writing native
        # datetime.datetime query params needs no conversion.
        data[field] = data[field].to_native()
    return ObservedEvidence(**data)


def _persist_fact(tx: neo4j.ManagedTransaction, fact: ObservedFactCandidate) -> None:
    if fact.relation_type not in KNOWN_RELATION_TYPES:
        raise ValueError(f"Unknown relation type: {fact.relation_type}")

    existing = _read_existing_evidence(tx, fact.evidence.id)
    merged = merge_evidence(existing, fact.evidence)
    tx.run(_MERGE_EVIDENCE_QUERY, id=merged.id, props=merged.model_dump(exclude={"id"}))

    query = _MERGE_FACT_RELATION_QUERY.format(relation_type=fact.relation_type)
    tx.run(query, subject_id=fact.subject_id, object_id=fact.object_id, evidence_id=merged.id)


def _persist_batch_tx(tx: neo4j.ManagedTransaction, batch: ObservationBatch) -> None:
    for entity in batch.entities:
        query = _MERGE_STUB_NODE_QUERY.format(label=entity.label)
        tx.run(query, id=entity.id, name=entity.name, discovery_status="OBSERVED_ONLY")

    # Sequential, not a bulk UNWIND: this is what correctly handles the same fact appearing more
    # than once within one OTLP batch - each read sees the previous iteration's already-written
    # merge within this same transaction. A later "optimize to UNWIND" edit would silently break
    # within-batch accumulation, since UNWIND rows don't get Python-level merge_evidence semantics.
    for fact in batch.facts:
        _persist_fact(tx, fact)


def persist_observation_batch(driver: neo4j.Driver, database: str, batch: ObservationBatch) -> None:
    """Persists an ObservationBatch's entities/facts to Neo4j (spec §36) - the first H4 write path.
    UnresolvedObservations are never persisted: purely diagnostic, no graph-model place for them."""
    with open_session(driver, database=database) as session:
        ensure_schema(session)
        session.execute_write(_persist_batch_tx, batch)
