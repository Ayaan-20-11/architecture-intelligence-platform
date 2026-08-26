from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DiscoveryStatus(StrEnum):
    """Whether a graph entity is known from declared sources or only from runtime observation
    (spec §13). Shared across the service/operation/queue resolvers, not service-specific."""

    DECLARED = "DECLARED"
    OBSERVED_ONLY = "OBSERVED_ONLY"


class RuntimeSpan(BaseModel):
    """Temporary OTLP ingestion model (spec §10) - never persisted to Neo4j. Decoded from a raw
    OTLP/HTTP export by app.telemetry.otlp_receiver; consumed and discarded by downstream
    resolvers/aggregators in later H4 iterations."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None

    span_name: str
    span_kind: str

    service_name: str
    service_namespace: str | None = None
    service_version: str | None = None
    service_instance_id: str | None = None

    environment: str | None = None

    start_time: datetime
    end_time: datetime

    attributes: dict[str, Any] = Field(default_factory=dict)
