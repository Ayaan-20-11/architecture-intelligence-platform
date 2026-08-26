from datetime import UTC, datetime
from typing import Any

from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import Span

from app.telemetry.model import RuntimeSpan
from app.telemetry.semconv import resources as semconv_resources

_SPAN_KIND_NAMES = {
    Span.SPAN_KIND_UNSPECIFIED: "UNSPECIFIED",
    Span.SPAN_KIND_INTERNAL: "INTERNAL",
    Span.SPAN_KIND_SERVER: "SERVER",
    Span.SPAN_KIND_CLIENT: "CLIENT",
    Span.SPAN_KIND_PRODUCER: "PRODUCER",
    Span.SPAN_KIND_CONSUMER: "CONSUMER",
}


class OtlpDecodeError(ValueError):
    """Raised when a raw OTLP/HTTP payload is not a valid ExportTraceServiceRequest - the whole
    batch is unusable, unlike a single resource block missing service.name (see below)."""


def _any_value_to_python(value: AnyValue) -> Any:
    """Unwraps a protobuf AnyValue oneof into a plain Python value. Expected to be reused (not
    duplicated) by later H4 iterations' resolvers, which read their own allowlisted attributes."""
    which = value.WhichOneof("value")
    if which is None:
        return None
    if which == "array_value":
        return [_any_value_to_python(v) for v in value.array_value.values]
    if which == "kvlist_value":
        return _attributes_to_dict(value.kvlist_value.values)
    return getattr(value, which)


def _attributes_to_dict(attributes: list[KeyValue]) -> dict[str, Any]:
    return {kv.key: _any_value_to_python(kv.value) for kv in attributes}


def _resource_identity(resource: Resource) -> dict[str, str | None]:
    attrs = _attributes_to_dict(resource.attributes)
    return {
        "service_name": attrs.get(semconv_resources.SERVICE_NAME),
        "service_namespace": attrs.get(semconv_resources.SERVICE_NAMESPACE),
        "service_version": attrs.get(semconv_resources.SERVICE_VERSION),
        "service_instance_id": attrs.get(semconv_resources.SERVICE_INSTANCE_ID),
        "environment": attrs.get(semconv_resources.DEPLOYMENT_ENVIRONMENT_NAME),
    }


def _to_datetime(unix_nano: int) -> datetime:
    return datetime.fromtimestamp(unix_nano / 1e9, tz=UTC)


def decode_export_request(raw: bytes) -> list[RuntimeSpan]:
    """Decodes an OTLP/HTTP protobuf ExportTraceServiceRequest into RuntimeSpans (spec §8/§10)."""
    request = ExportTraceServiceRequest()
    try:
        request.ParseFromString(raw)
    except DecodeError as exc:
        raise OtlpDecodeError(f"malformed OTLP trace payload: {exc}") from exc

    spans: list[RuntimeSpan] = []
    for resource_spans in request.resource_spans:
        identity = _resource_identity(resource_spans.resource)
        if not identity["service_name"]:
            # Can't identify the reporting service - a routine shape in a multi-service batch
            # export, not a corrupted request, so skip just this block rather than the whole batch.
            continue
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                spans.append(
                    RuntimeSpan(
                        trace_id=span.trace_id.hex(),
                        span_id=span.span_id.hex(),
                        parent_span_id=span.parent_span_id.hex() or None,
                        span_name=span.name,
                        span_kind=_SPAN_KIND_NAMES.get(span.kind, "UNSPECIFIED"),
                        start_time=_to_datetime(span.start_time_unix_nano),
                        end_time=_to_datetime(span.end_time_unix_nano),
                        attributes=_attributes_to_dict(span.attributes),
                        **identity,
                    )
                )
    return spans
