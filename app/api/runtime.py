from datetime import UTC, datetime

import neo4j
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.analysis.runtime import (
    confirmed_relations,
    declared_only_relations,
    default_since,
    observed_only_relations,
    observed_relations,
    service_runtime_profile,
    telemetry_coverage,
)
from app.deps import get_read_session, get_settings
from app.settings import Settings

runtime_router = APIRouter(prefix="/api/runtime", tags=["runtime"])
runtime_analysis_router = APIRouter(prefix="/api/analysis/runtime", tags=["runtime-analysis"])


class RuntimeWindow(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: datetime = Field(alias="from")
    to: datetime


class RuntimeRelationOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    source_id: str = Field(alias="sourceId")
    source: str
    relation: str
    target_id: str = Field(alias="targetId")
    target: str
    environment: str
    status: str
    first_seen: datetime = Field(alias="firstSeen")
    last_seen: datetime = Field(alias="lastSeen")
    observation_count: int = Field(alias="observationCount")


class RuntimeRelationListOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    environment: str | None
    window: RuntimeWindow
    relations: list[RuntimeRelationOut]


class DeclaredOnlyRelationOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    source_id: str = Field(alias="sourceId")
    source: str
    relation: str
    target_id: str = Field(alias="targetId")
    target: str
    environment: str
    status: str
    telemetry_coverage_available: bool = Field(alias="telemetryCoverageAvailable")


class DeclaredOnlyListOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    environment: str
    window: RuntimeWindow
    relations: list[DeclaredOnlyRelationOut]


class ServiceCoverageOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    service_id: str = Field(alias="serviceId")
    service: str
    environment: str
    http_observed: bool = Field(alias="httpObserved")
    messaging_observed: bool = Field(alias="messagingObserved")
    spans_observed: bool = Field(alias="spansObserved")


class CoverageListOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    environment: str
    window: RuntimeWindow
    services: list[ServiceCoverageOut]


class ServiceRuntimeRelationOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    relation: str
    target_id: str = Field(alias="targetId")
    target: str
    status: str
    first_seen: datetime | None = Field(alias="firstSeen")
    last_seen: datetime | None = Field(alias="lastSeen")
    observation_count: int | None = Field(alias="observationCount")
    telemetry_coverage_available: bool | None = Field(alias="telemetryCoverageAvailable")


class ServiceRuntimeProfileOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    service_id: str = Field(alias="serviceId")
    service: str
    environment: str
    window: RuntimeWindow
    coverage: ServiceCoverageOut
    relations: list[ServiceRuntimeRelationOut]


def _resolve_window(
    settings: Settings, since: datetime | None, until: datetime | None
) -> tuple[datetime, datetime]:
    resolved_since = since or default_since(settings.config.runtime_analysis.default_window_hours)
    resolved_until = until or datetime.now(UTC)
    return resolved_since, resolved_until


def _native(value: datetime | None) -> datetime | None:
    """Neo4j returns temporal properties as neo4j.time.DateTime, not datetime.datetime - Pydantic
    rejects it outright when serializing (same gotcha aggregator.py's own .to_native() fix
    addresses on the read side); RelationObservation/DeclaredOnlyRelation are plain dataclasses so
    they never hit this, but the Pydantic response models here do."""
    return value.to_native() if hasattr(value, "to_native") else value


def _coverage_out(environment: str, c) -> ServiceCoverageOut:
    return ServiceCoverageOut(
        service_id=c.service_id,
        service=c.service_name,
        environment=environment,
        http_observed=c.http_observed,
        messaging_observed=c.messaging_observed,
        spans_observed=c.spans_observed,
    )


@runtime_router.get("/relations", response_model=RuntimeRelationListOut)
def get_observed_relations(
    environment: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    relation_type: str | None = Query(default=None, alias="relationType"),
    from_id: str | None = Query(default=None, alias="from"),
    to_id: str | None = Query(default=None, alias="to"),
    session: neo4j.Session = Depends(get_read_session),
    settings: Settings = Depends(get_settings),
) -> RuntimeRelationListOut:
    """O1 (spec §42/§47). environment stays optional/"any" here, unlike O2-O5 - matches
    observed_relations()'s own filter framing."""
    resolved_since, resolved_until = _resolve_window(settings, since, until)
    rows = observed_relations(
        session,
        environment=environment,
        from_id=from_id,
        to_id=to_id,
        relation_type=relation_type,
        since=resolved_since,
        until=until,
    )
    return RuntimeRelationListOut(
        environment=environment,
        window=RuntimeWindow(from_=resolved_since, to=resolved_until),
        relations=[
            RuntimeRelationOut(
                source_id=r.source_id,
                source=r.source_name,
                relation=r.relation_type,
                target_id=r.target_id,
                target=r.target_name,
                environment=r.environment,
                status="OBSERVED",
                first_seen=_native(r.first_seen),
                last_seen=_native(r.last_seen),
                observation_count=r.observation_count,
            )
            for r in rows
        ],
    )


@runtime_router.get("/services/{service_id}", response_model=ServiceRuntimeProfileOut)
def get_service_runtime_profile(
    service_id: str,
    environment: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    session: neo4j.Session = Depends(get_read_session),
    settings: Settings = Depends(get_settings),
) -> ServiceRuntimeProfileOut:
    """Per-service runtime profile (11G design - see service_runtime_profile()'s docstring for the
    composition rationale). Not a literal spec §47 JSON example, but the exact endpoint path is."""
    env = environment or settings.config.runtime_analysis.default_environment
    resolved_since, resolved_until = _resolve_window(settings, since, until)
    profile = service_runtime_profile(
        session, service_id=service_id, environment=env, since=resolved_since, until=until
    )
    if profile is None:
        raise HTTPException(status_code=404, detail=f"service not found: {service_id}")
    return ServiceRuntimeProfileOut(
        service_id=profile.service_id,
        service=profile.service_name,
        environment=env,
        window=RuntimeWindow(from_=resolved_since, to=resolved_until),
        coverage=_coverage_out(env, profile.coverage),
        relations=[
            ServiceRuntimeRelationOut(
                relation=r.relation_type,
                target_id=r.target_id,
                target=r.target_name,
                status=r.status,
                first_seen=_native(r.first_seen),
                last_seen=_native(r.last_seen),
                observation_count=r.observation_count,
                telemetry_coverage_available=r.telemetry_coverage_available,
            )
            for r in profile.relations
        ],
    )


def _relation_list(
    session: neo4j.Session,
    settings: Settings,
    environment: str | None,
    since: datetime | None,
    until: datetime | None,
    status_label: str,
    analysis_fn,
) -> RuntimeRelationListOut:
    env = environment or settings.config.runtime_analysis.default_environment
    resolved_since, resolved_until = _resolve_window(settings, since, until)
    rows = analysis_fn(session, environment=env, since=resolved_since, until=until)
    return RuntimeRelationListOut(
        environment=env,
        window=RuntimeWindow(from_=resolved_since, to=resolved_until),
        relations=[
            RuntimeRelationOut(
                source_id=r.source_id,
                source=r.source_name,
                relation=r.relation_type,
                target_id=r.target_id,
                target=r.target_name,
                environment=r.environment,
                status=status_label,
                first_seen=_native(r.first_seen),
                last_seen=_native(r.last_seen),
                observation_count=r.observation_count,
            )
            for r in rows
        ],
    )


@runtime_analysis_router.get("/confirmed", response_model=RuntimeRelationListOut)
def get_confirmed(
    environment: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    session: neo4j.Session = Depends(get_read_session),
    settings: Settings = Depends(get_settings),
) -> RuntimeRelationListOut:
    """O2 (spec §43/§47)."""
    return _relation_list(
        session, settings, environment, since, until, "CONFIRMED", confirmed_relations
    )


@runtime_analysis_router.get("/observed-only", response_model=RuntimeRelationListOut)
def get_observed_only(
    environment: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    session: neo4j.Session = Depends(get_read_session),
    settings: Settings = Depends(get_settings),
) -> RuntimeRelationListOut:
    """O3 (spec §44/§47/§48 - the one literal example response this endpoint's shape follows)."""
    return _relation_list(
        session, settings, environment, since, until, "OBSERVED_ONLY", observed_only_relations
    )


@runtime_analysis_router.get("/declared-only", response_model=DeclaredOnlyListOut)
def get_declared_only(
    environment: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    session: neo4j.Session = Depends(get_read_session),
    settings: Settings = Depends(get_settings),
) -> DeclaredOnlyListOut:
    """O4 (spec §45/§47). status is always the literal NOT_OBSERVED_IN_WINDOW (H4.16)."""
    env = environment or settings.config.runtime_analysis.default_environment
    resolved_since, resolved_until = _resolve_window(settings, since, until)
    rows = declared_only_relations(session, environment=env, since=resolved_since, until=until)
    return DeclaredOnlyListOut(
        environment=env,
        window=RuntimeWindow(from_=resolved_since, to=resolved_until),
        relations=[
            DeclaredOnlyRelationOut(
                source_id=r.source_id,
                source=r.source_name,
                relation=r.relation_type,
                target_id=r.target_id,
                target=r.target_name,
                environment=r.environment,
                status=r.status,
                telemetry_coverage_available=r.telemetry_coverage_available,
            )
            for r in rows
        ],
    )


@runtime_analysis_router.get("/coverage", response_model=CoverageListOut)
def get_coverage(
    environment: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    service_id: list[str] | None = Query(default=None, alias="serviceId"),
    session: neo4j.Session = Depends(get_read_session),
    settings: Settings = Depends(get_settings),
) -> CoverageListOut:
    """O5 (spec §46/§47). serviceId is repeatable (?serviceId=a&serviceId=b); omitted = all services."""
    env = environment or settings.config.runtime_analysis.default_environment
    resolved_since, resolved_until = _resolve_window(settings, since, until)
    rows = telemetry_coverage(
        session, environment=env, since=resolved_since, until=until, service_ids=service_id
    )
    return CoverageListOut(
        environment=env,
        window=RuntimeWindow(from_=resolved_since, to=resolved_until),
        services=[_coverage_out(env, r) for r in rows],
    )
