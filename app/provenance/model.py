from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SourceType(StrEnum):
    OPENAPI = "OPENAPI"
    ASYNCAPI = "ASYNCAPI"
    MANIFEST = "MANIFEST"
    OPENTELEMETRY = "OPENTELEMETRY"


class EvidenceType(StrEnum):
    DECLARED = "DECLARED"
    OBSERVED = "OBSERVED"


class Provenance(BaseModel):
    id: str
    source_type: str  # OPENAPI | ASYNCAPI | MANIFEST | OPENTELEMETRY
    source_file: str
    source_revision: str | None = None
    evidence_type: str = "DECLARED"


class ObservedEvidence(Provenance):
    """A single-observation evidence seed (spec §16) - a degenerate bucket-of-one produced by a
    resolver (e.g. app.telemetry.adapter). The Aggregator (H4 Iteration 11E) merges many seeds for
    the same bucket into the real persisted, time-bounded evidence (summing observation_count,
    expanding first_seen/last_seen, capping sample_trace_ids at 5)."""

    source_type: str = SourceType.OPENTELEMETRY
    source_file: str = "opentelemetry"
    evidence_type: str = EvidenceType.OBSERVED

    environment: str
    bucket_start: datetime
    bucket_end: datetime
    first_seen: datetime
    last_seen: datetime
    observation_count: int
    sample_trace_ids: list[str] = Field(default_factory=list)
    service_version: str | None = None
    # How this evidence was derived (11H R3/spec §14 - see app.telemetry.model.CorrelationMode for
    # the allowed values). Optional so pre-11H-C construction sites keep working unmodified.
    correlation_mode: str | None = None
