from fastapi import APIRouter, HTTPException, Request, Response
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

from app.telemetry.otlp_receiver import OtlpDecodeError, decode_export_request

router = APIRouter(tags=["telemetry"])

_OTLP_CONTENT_TYPE = "application/x-protobuf"


@router.post("/v1/traces")
async def post_traces(request: Request) -> Response:
    """OTLP/HTTP trace ingestion (spec §8) - decodes into RuntimeSpans and discards them; no graph
    update happens yet (Iteration 11A, spec §67)."""
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith(_OTLP_CONTENT_TYPE):
        raise HTTPException(
            status_code=415,
            detail=f"unsupported content-type: {content_type!r}, expected {_OTLP_CONTENT_TYPE!r}",
        )

    raw = await request.body()
    try:
        decode_export_request(raw)
    except OtlpDecodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=ExportTraceServiceResponse().SerializeToString(),
        media_type=_OTLP_CONTENT_TYPE,
    )
