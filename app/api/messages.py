import neo4j
from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_read_session

router = APIRouter(prefix="/api/messages", tags=["messages"])

_FIELDS = "m.id AS id, m.name AS name, m.version AS version, m.schema_id AS schema_id"
_LIST_QUERY = f"MATCH (m:Message) RETURN {_FIELDS} ORDER BY m.name"
_GET_QUERY = f"MATCH (m:Message {{id: $id}}) RETURN {_FIELDS}"


@router.get("")
def list_messages(session: neo4j.Session = Depends(get_read_session)) -> list[dict]:
    return [record.data() for record in session.run(_LIST_QUERY)]


@router.get("/{message_id}")
def get_message(message_id: str, session: neo4j.Session = Depends(get_read_session)) -> dict:
    record = session.run(_GET_QUERY, id=message_id).single()
    if record is None:
        raise HTTPException(status_code=404, detail=f"message not found: {message_id}")
    return record.data()
