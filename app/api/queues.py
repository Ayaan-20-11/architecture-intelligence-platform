import neo4j
from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_read_session

router = APIRouter(prefix="/api/queues", tags=["queues"])

_FIELDS = "q.id AS id, q.name AS name, q.protocol AS protocol, q.namespace AS namespace, q.queue_type AS queue_type"
_LIST_QUERY = f"MATCH (q:Queue) RETURN {_FIELDS} ORDER BY q.name"
_GET_QUERY = f"MATCH (q:Queue {{id: $id}}) RETURN {_FIELDS}"


@router.get("")
def list_queues(session: neo4j.Session = Depends(get_read_session)) -> list[dict]:
    return [record.data() for record in session.run(_LIST_QUERY)]


@router.get("/{queue_id}")
def get_queue(queue_id: str, session: neo4j.Session = Depends(get_read_session)) -> dict:
    record = session.run(_GET_QUERY, id=queue_id).single()
    if record is None:
        raise HTTPException(status_code=404, detail=f"queue not found: {queue_id}")
    return record.data()
