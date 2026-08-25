import neo4j
from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_read_session

router = APIRouter(prefix="/api/services", tags=["services"])

_LIST_QUERY = (
    "MATCH (s:Service) RETURN s.id AS id, s.name AS name, s.version AS version ORDER BY s.name"
)
_GET_QUERY = "MATCH (s:Service {id: $id}) RETURN s.id AS id, s.name AS name, s.version AS version"
_EVIDENCE_QUERY = (
    "MATCH (:Service {id: $id})-[r]-() "
    "UNWIND coalesce(r.evidence_ids, []) AS eid "
    "MATCH (e:Evidence {id: eid}) "
    "RETURN DISTINCT e.id AS id, e.source_type AS source_type, e.source_file AS source_file, "
    "e.source_revision AS source_revision, e.evidence_type AS evidence_type "
    "ORDER BY e.id"
)


@router.get("")
def list_services(session: neo4j.Session = Depends(get_read_session)) -> list[dict]:
    return [record.data() for record in session.run(_LIST_QUERY)]


@router.get("/{service_id}")
def get_service(service_id: str, session: neo4j.Session = Depends(get_read_session)) -> dict:
    record = session.run(_GET_QUERY, id=service_id).single()
    if record is None:
        raise HTTPException(status_code=404, detail=f"service not found: {service_id}")
    return record.data()


@router.get("/{service_id}/evidence")
def get_service_evidence(
    service_id: str, session: neo4j.Session = Depends(get_read_session)
) -> list[dict]:
    """Evidence backing every relation incident to this service (spec §4.10, AC13)."""
    if session.run(_GET_QUERY, id=service_id).single() is None:
        raise HTTPException(status_code=404, detail=f"service not found: {service_id}")
    return [record.data() for record in session.run(_EVIDENCE_QUERY, id=service_id)]
