import neo4j
from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_read_session

router = APIRouter(prefix="/api/evidence", tags=["evidence"])

_FIELDS = (
    "e.id AS id, e.source_type AS source_type, e.source_file AS source_file, "
    "e.source_revision AS source_revision, e.evidence_type AS evidence_type"
)
_LIST_QUERY = f"MATCH (e:Evidence) RETURN {_FIELDS} ORDER BY e.id"
_GET_QUERY = f"MATCH (e:Evidence {{id: $id}}) RETURN {_FIELDS}"


@router.get("")
def list_evidence(session: neo4j.Session = Depends(get_read_session)) -> list[dict]:
    return [record.data() for record in session.run(_LIST_QUERY)]


@router.get("/{evidence_id}")
def get_evidence(evidence_id: str, session: neo4j.Session = Depends(get_read_session)) -> dict:
    record = session.run(_GET_QUERY, id=evidence_id).single()
    if record is None:
        raise HTTPException(status_code=404, detail=f"evidence not found: {evidence_id}")
    return record.data()
