import neo4j
from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_read_session

router = APIRouter(prefix="/api/queues", tags=["queues"])

_FIELDS = "q.id AS id, q.name AS name, q.protocol AS protocol, q.namespace AS namespace, q.queue_type AS queue_type"
_LIST_QUERY = f"MATCH (q:Queue) RETURN {_FIELDS} ORDER BY q.name"
_GET_QUERY = f"MATCH (q:Queue {{id: $id}}) RETURN {_FIELDS}"
_EVIDENCE_QUERY = (
    "MATCH (:Queue {id: $id})-[r]-() "
    "UNWIND coalesce(r.evidence_ids, []) AS eid "
    "MATCH (e:Evidence {id: eid}) "
    "RETURN DISTINCT e.id AS id, e.source_type AS source_type, e.source_file AS source_file, "
    "e.source_revision AS source_revision, e.evidence_type AS evidence_type "
    "ORDER BY e.id"
)


@router.get("")
def list_queues(session: neo4j.Session = Depends(get_read_session)) -> list[dict]:
    return [record.data() for record in session.run(_LIST_QUERY)]


@router.get("/{queue_id}")
def get_queue(queue_id: str, session: neo4j.Session = Depends(get_read_session)) -> dict:
    record = session.run(_GET_QUERY, id=queue_id).single()
    if record is None:
        raise HTTPException(status_code=404, detail=f"queue not found: {queue_id}")
    return record.data()


@router.get("/{queue_id}/evidence")
def get_queue_evidence(
    queue_id: str, session: neo4j.Session = Depends(get_read_session)
) -> list[dict]:
    """Evidence backing every relation incident to this queue (spec §4.10, AC13)."""
    if session.run(_GET_QUERY, id=queue_id).single() is None:
        raise HTTPException(status_code=404, detail=f"queue not found: {queue_id}")
    return [record.data() for record in session.run(_EVIDENCE_QUERY, id=queue_id)]
