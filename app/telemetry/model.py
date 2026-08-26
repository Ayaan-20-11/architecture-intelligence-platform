from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.provenance.model import ObservedEvidence


class DiscoveryStatus(StrEnum):
    """Whether a graph entity is known from declared sources or only from runtime observation
    (spec §13). Shared across the service/operation/queue resolvers, not service-specific."""

    DECLARED = "DECLARED"
    OBSERVED_ONLY = "OBSERVED_ONLY"


class CorrelationMode(StrEnum):
    """How an observed fact's evidence was derived (11H R3/spec §14) - a source of named
    constants only; ObservedEvidence.correlation_mode itself stays a plain str, mirroring how
    Provenance.evidence_type stays a plain str even though EvidenceType exists as a companion
    enum. CLIENT_SERVER is the strongest signal (both sides seen, in-batch or cross-batch);
    CLIENT_ONLY/SERVER_ONLY are partial-instrumentation signals; the three MESSAGING_* modes
    distinguish send/receive/process even though RECEIVES_FROM covers both receive and process at
    the relation-type level."""

    CLIENT_SERVER = "CLIENT_SERVER"
    CLIENT_ONLY = "CLIENT_ONLY"
    SERVER_ONLY = "SERVER_ONLY"
    MESSAGING_SEND = "MESSAGING_SEND"
    MESSAGING_RECEIVE = "MESSAGING_RECEIVE"
    MESSAGING_PROCESS = "MESSAGING_PROCESS"


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


def day_bucket(timestamp: datetime) -> tuple[datetime, datetime]:
    """Truncates a timestamp to its UTC calendar day (spec §17: bucket = 1 day), returning
    (day_start, day_start + 1 day)."""
    day_start = datetime(timestamp.year, timestamp.month, timestamp.day, tzinfo=timestamp.tzinfo)
    return day_start, day_start + timedelta(days=1)


class ObservedFactCandidate(BaseModel):
    """A single resolved-but-not-yet-aggregated observation (spec §34), produced by a resolver
    (e.g. app.telemetry.adapter) - not persisted to Neo4j; the Aggregator (Iteration 11E) merges
    many of these into real graph facts/evidence."""

    subject_id: str
    relation_type: str
    object_id: str

    environment: str

    timestamp: datetime
    trace_id: str | None = None
    source_service_version: str | None = None

    evidence: ObservedEvidence


class ObservedOnlyEntity(BaseModel):
    """Just enough information for a later Aggregator to MERGE a stub node for a previously-
    undocumented Service/Operation/Queue - a deliberate simplification of spec §35's
    ArchitectureEntity, which the spec references but never defines."""

    id: str
    label: Literal["Service", "Operation", "Queue"]
    name: str


class UnresolvedObservation(BaseModel):
    """A correlated observation that couldn't be turned into a fact (spec §23 Fall C and similar) -
    trace_id plus a short reason code (never raw span attributes/URLs, spec §31)."""

    trace_id: str
    reason: str


class ObservationBatch(BaseModel):
    """A resolver's output for one decoded OTLP batch (spec §35)."""

    entities: list[ObservedOnlyEntity] = Field(default_factory=list)
    facts: list[ObservedFactCandidate] = Field(default_factory=list)
    unresolved: list[UnresolvedObservation] = Field(default_factory=list)
