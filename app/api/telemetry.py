import neo4j
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

from app.deps import get_driver, get_settings
from app.graph.repository import open_session
from app.settings import Settings
from app.telemetry.adapter import adapt
from app.telemetry.aggregator import persist_observation_batch
from app.telemetry.operation_resolver import fetch_operation_candidates
from app.telemetry.otlp_receiver import OtlpDecodeError, decode_export_request
from app.telemetry.queue_resolver import fetch_queue_candidates
from app.telemetry.service_resolver import fetch_candidates

router = APIRouter(tags=["telemetry"])

_OTLP_CONTENT_TYPE = "application/x-protobuf"


@router.post("/v1/traces")
async def post_traces(
    request: Request,
    driver: neo4j.Driver = Depends(get_driver),
    settings: Settings = Depends(get_settings),
) -> Response:
    """OTLP/HTTP trace ingestion (spec §8): decode -> resolve against declared data -> persist
    observed facts/evidence (spec §36, Iteration 11E). Content-type/decode validation happens
    before any Neo4j access, so a malformed request never touches the graph."""
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith(_OTLP_CONTENT_TYPE):
        raise HTTPException(
            status_code=415,
            detail=f"unsupported content-type: {content_type!r}, expected {_OTLP_CONTENT_TYPE!r}",
        )

    raw = await request.body()
    try:
        spans = decode_export_request(raw)
    except OtlpDecodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    database = settings.config.graph.database
    with open_session(driver, database=database, read_only=True) as session:
        service_candidates = fetch_candidates(session)
        operation_candidates = fetch_operation_candidates(session)
        queue_candidates = fetch_queue_candidates(session)

    batch = adapt(
        spans,
        service_candidates=service_candidates,
        operation_candidates=operation_candidates,
        queue_candidates=queue_candidates,
        service_aliases=settings.config.telemetry.service_aliases,
        queue_aliases=settings.config.telemetry.queue_aliases,
    )
    persist_observation_batch(driver, database, batch)

    return Response(
        content=ExportTraceServiceResponse().SerializeToString(),
        media_type=_OTLP_CONTENT_TYPE,
    )
