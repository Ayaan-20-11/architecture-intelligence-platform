import neo4j
from fastapi import APIRouter, Depends, Query

from app.analysis.blast_radius import DEFAULT_MAX_DEPTH, blast_radius
from app.analysis.queues import (
    consumers_of_queue,
    queues_without_consumers,
    queues_without_senders,
    senders_of_queue,
)
from app.deps import get_read_session

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/queues/{queue_id}/senders")
def get_senders(queue_id: str, session: neo4j.Session = Depends(get_read_session)):
    """A1 (spec §13.1)."""
    return senders_of_queue(session, queue_id)


@router.get("/queues/{queue_id}/consumers")
def get_consumers(queue_id: str, session: neo4j.Session = Depends(get_read_session)):
    """A2 (spec §13.2)."""
    return consumers_of_queue(session, queue_id)


@router.get("/queues/without-consumers")
def get_queues_without_consumers(session: neo4j.Session = Depends(get_read_session)):
    """A3 (spec §13.3)."""
    return queues_without_consumers(session)


@router.get("/queues/without-senders")
def get_queues_without_senders(session: neo4j.Session = Depends(get_read_session)):
    """A4 (spec §13.4)."""
    return queues_without_senders(session)


@router.get("/services/{service_id}/blast-radius")
def get_blast_radius(
    service_id: str,
    depth: int = Query(default=DEFAULT_MAX_DEPTH, ge=1),
    session: neo4j.Session = Depends(get_read_session),
):
    """A5 (spec §13.5)."""
    return blast_radius(session, service_id, max_depth=depth)
