import neo4j
from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_read_session

router = APIRouter(prefix="/api/services", tags=["services"])

_LIST_QUERY = (
    "MATCH (s:Service) RETURN s.id AS id, s.name AS name, s.version AS version ORDER BY s.name"
)
_GET_QUERY = "MATCH (s:Service {id: $id}) RETURN s.id AS id, s.name AS name, s.version AS version"


@router.get("")
def list_services(session: neo4j.Session = Depends(get_read_session)) -> list[dict]:
    return [record.data() for record in session.run(_LIST_QUERY)]


@router.get("/{service_id}")
def get_service(service_id: str, session: neo4j.Session = Depends(get_read_session)) -> dict:
    record = session.run(_GET_QUERY, id=service_id).single()
    if record is None:
        raise HTTPException(status_code=404, detail=f"service not found: {service_id}")
    return record.data()
