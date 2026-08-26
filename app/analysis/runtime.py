from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import neo4j

NOT_OBSERVED_IN_WINDOW = "NOT_OBSERVED_IN_WINDOW"
DEFAULT_WINDOW_HOURS = 24
DEFAULT_ENVIRONMENT = "production"

# 11H R7/spec §11.2 - qualitative coverage classification for a NOT_OBSERVED_IN_WINDOW finding.
# Deliberately a fixed small vocabulary, not a numeric confidence score (spec §11.2 explicitly
# doesn't require one).
COVERAGE_SUFFICIENT = "SUFFICIENT"
COVERAGE_PARTIAL = "PARTIAL"
COVERAGE_NONE = "NONE"
COVERAGE_UNKNOWN = "UNKNOWN"

# Shared building blocks for the CALLS branch used by O1-O4: CALLS always goes
# (Service)-[r]->(Operation), never Service->Service, and PROVIDES is only ever written by the
# declared OpenAPI import path (never by the H4 telemetry pipeline for an undeclared/Fall-B
# operation stub). An inner join through PROVIDES would therefore silently drop exactly the rows
# O3 exists to surface (undeclared operations/services) - every query below uses OPTIONAL MATCH
# and a coalesce() fallback chain for the target's identity instead.
_CALLS_TARGET_ID_EXPR = "coalesce(provider.id, o.id)"
_CALLS_TARGET_NAME_EXPR = "coalesce(provider.name, o.name, o.method + ' ' + o.path, o.id)"
_CALLS_TARGET = f"{_CALLS_TARGET_ID_EXPR} AS target_id, {_CALLS_TARGET_NAME_EXPR} AS target_name"

_OBSERVED_EXISTS = (
    "EXISTS { UNWIND r.evidence_ids AS eid MATCH (e:Evidence {id: eid}) "
    "WHERE e.evidence_type = 'OBSERVED' AND e.environment = $environment "
    "AND e.last_seen >= $since AND ($until IS NULL OR e.last_seen <= $until) }"
)
_NOT_OBSERVED_EXISTS = (
    "NOT EXISTS { UNWIND r.evidence_ids AS eid MATCH (e:Evidence {id: eid}) "
    "WHERE e.evidence_type = 'OBSERVED' AND e.environment = $environment "
    "AND e.last_seen >= $since AND ($until IS NULL OR e.last_seen <= $until) }"
)
_DECLARED_EXISTS = (
    "EXISTS { UNWIND r.evidence_ids AS eid2 MATCH (e2:Evidence {id: eid2}) "
    "WHERE e2.evidence_type = 'DECLARED' }"
)
_NOT_DECLARED_EXISTS = (
    "NOT EXISTS { UNWIND r.evidence_ids AS eid2 MATCH (e2:Evidence {id: eid2}) "
    "WHERE e2.evidence_type = 'DECLARED' }"
)


def default_since(hours: int = DEFAULT_WINDOW_HOURS) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


@dataclass(frozen=True)
class RelationObservation:
    """A relation with matching OBSERVED evidence - every row here was actually seen at runtime
    (used by O1/O2/O3). Multiple daily evidence buckets within the window are aggregated into one
    summary row per relation."""

    source_id: str
    source_name: str
    relation_type: str
    target_id: str
    target_name: str
    environment: str
    first_seen: datetime
    last_seen: datetime
    observation_count: int


_O1_QUERY = (
    "MATCH (a:Service)-[r:CALLS]->(o:Operation) "
    "OPTIONAL MATCH (o)<-[:PROVIDES]-(provider:Service) "
    # WITH is required here, not cosmetic: a WHERE clause directly after OPTIONAL MATCH is parsed
    # as part of that OPTIONAL MATCH's own pattern (Cypher grammar), not as a row filter - a false
    # condition just null-pads `provider` instead of dropping the row. This silently broke O1's
    # to_id/relation_type/from_id filters whenever they'd otherwise exclude a CALLS row (the row
    # survived anyway, with a wrongly-nulled provider feeding _CALLS_TARGET_ID_EXPR's fallback).
    "WITH a, r, o, provider "
    "WHERE ($relation_type IS NULL OR $relation_type = 'CALLS') "
    "AND ($from_id IS NULL OR a.id = $from_id) "
    f"AND ($to_id IS NULL OR {_CALLS_TARGET_ID_EXPR} = $to_id) "
    "UNWIND coalesce(r.evidence_ids, []) AS eid "
    "MATCH (e:Evidence {id: eid}) "
    "WHERE e.evidence_type = 'OBSERVED' "
    "AND ($environment IS NULL OR e.environment = $environment) "
    "AND e.last_seen >= $since "
    "AND ($until IS NULL OR e.last_seen <= $until) "
    f"RETURN a.id AS source_id, a.name AS source_name, 'CALLS' AS relation_type, {_CALLS_TARGET}, "
    "e.environment AS environment, "
    "min(e.first_seen) AS first_seen, max(e.last_seen) AS last_seen, "
    "sum(e.observation_count) AS observation_count "
    "UNION "
    "MATCH (a:Service)-[r:SENDS|RECEIVES_FROM]->(b:Queue) "
    "WHERE ($relation_type IS NULL OR $relation_type = type(r)) "
    "AND ($from_id IS NULL OR a.id = $from_id) AND ($to_id IS NULL OR b.id = $to_id) "
    "UNWIND coalesce(r.evidence_ids, []) AS eid "
    "MATCH (e:Evidence {id: eid}) "
    "WHERE e.evidence_type = 'OBSERVED' AND ($environment IS NULL OR e.environment = $environment) "
    "AND e.last_seen >= $since AND ($until IS NULL OR e.last_seen <= $until) "
    "RETURN a.id AS source_id, a.name AS source_name, type(r) AS relation_type, "
    "b.id AS target_id, b.name AS target_name, e.environment AS environment, "
    "min(e.first_seen) AS first_seen, max(e.last_seen) AS last_seen, "
    "sum(e.observation_count) AS observation_count "
    "ORDER BY source_id, target_id"
)


def observed_relations(
    session: neo4j.Session,
    *,
    environment: str | None = None,
    from_id: str | None = None,
    to_id: str | None = None,
    relation_type: str | None = None,
    since: datetime,
    until: datetime | None = None,
) -> list[RelationObservation]:
    """O1 - which architecture relationships were actually observed (spec §42). All filters are
    optional - a plain call with no filters is a valid raw listing."""
    records = session.run(
        _O1_QUERY,
        environment=environment,
        from_id=from_id,
        to_id=to_id,
        relation_type=relation_type,
        since=since,
        until=until,
    )
    return [RelationObservation(**record.data()) for record in records]


def _status_query(declared_guard: str, observed_guard: str) -> str:
    return (
        "MATCH (a:Service)-[r:CALLS]->(o:Operation) "
        "OPTIONAL MATCH (o)<-[:PROVIDES]-(provider:Service) "
        # See _O1_QUERY's comment - WHERE right after OPTIONAL MATCH filters the optional pattern,
        # not the row, so this WITH is required for the declared_guard/observed_guard EXISTS{}
        # checks to actually exclude non-matching rows instead of null-padding provider and
        # silently keeping them (which made O2/O3 return rows that belonged in the other's
        # category, or in O4, whenever the same environment had both CONFIRMED and DECLARED_ONLY/
        # OBSERVED_ONLY relations - i.e. essentially every non-trivial real graph).
        "WITH a, r, o, provider "
        f"WHERE {declared_guard} AND {observed_guard} "
        "UNWIND coalesce(r.evidence_ids, []) AS eid "
        "MATCH (e:Evidence {id: eid}) "
        "WHERE e.evidence_type = 'OBSERVED' AND e.environment = $environment "
        "AND e.last_seen >= $since AND ($until IS NULL OR e.last_seen <= $until) "
        f"RETURN a.id AS source_id, a.name AS source_name, 'CALLS' AS relation_type, {_CALLS_TARGET}, "
        "e.environment AS environment, "
        "min(e.first_seen) AS first_seen, max(e.last_seen) AS last_seen, "
        "sum(e.observation_count) AS observation_count "
        "UNION "
        "MATCH (a:Service)-[r:SENDS|RECEIVES_FROM]->(b:Queue) "
        f"WHERE {declared_guard} AND {observed_guard} "
        "UNWIND coalesce(r.evidence_ids, []) AS eid "
        "MATCH (e:Evidence {id: eid}) "
        "WHERE e.evidence_type = 'OBSERVED' AND e.environment = $environment "
        "AND e.last_seen >= $since AND ($until IS NULL OR e.last_seen <= $until) "
        "RETURN a.id AS source_id, a.name AS source_name, type(r) AS relation_type, "
        "b.id AS target_id, b.name AS target_name, e.environment AS environment, "
        "min(e.first_seen) AS first_seen, max(e.last_seen) AS last_seen, "
        "sum(e.observation_count) AS observation_count "
        "ORDER BY source_id, target_id"
    )


_O2_QUERY = _status_query(_DECLARED_EXISTS, _OBSERVED_EXISTS)
_O3_QUERY = _status_query(_NOT_DECLARED_EXISTS, _OBSERVED_EXISTS)


def confirmed_relations(
    session: neo4j.Session, *, environment: str, since: datetime, until: datetime | None = None
) -> list[RelationObservation]:
    """O2 - Declared ∩ Observed (spec §43/§38: D ∧ O => CONFIRMED). environment is required, not
    optional: the same fact can be CONFIRMED in production and DECLARED_ONLY in staging
    simultaneously, so a status-deriving function can't default to "any" environment."""
    records = session.run(_O2_QUERY, environment=environment, since=since, until=until)
    return [RelationObservation(**record.data()) for record in records]


def observed_only_relations(
    session: neo4j.Session, *, environment: str, since: datetime, until: datetime | None = None
) -> list[RelationObservation]:
    """O3 - Observed - Declared (spec §44/§38: ¬D ∧ O => OBSERVED_ONLY) - undocumented real
    dependencies. Spec calls this "probably the most important H4 analysis"."""
    records = session.run(_O3_QUERY, environment=environment, since=since, until=until)
    return [RelationObservation(**record.data()) for record in records]


@dataclass(frozen=True)
class DeclaredOnlyRelation:
    """A relation with DECLARED evidence but no matching OBSERVED evidence in the given
    environment/window (spec §45/§38: D ∧ ¬O => DECLARED_ONLY). status is always
    NOT_OBSERVED_IN_WINDOW - never "obsolete"/"unused"/"dead" (spec §40/H4.16)."""

    source_id: str
    source_name: str
    relation_type: str
    target_id: str
    target_name: str
    environment: str
    since: datetime
    status: str
    telemetry_coverage_available: bool
    coverage: str


_O4_QUERY = (
    "MATCH (a:Service)-[r:CALLS]->(o:Operation) "
    "OPTIONAL MATCH (o)<-[:PROVIDES]-(provider:Service) "
    # Same fix as _O1_QUERY/_status_query - see their comments.
    "WITH a, r, o, provider "
    f"WHERE {_DECLARED_EXISTS} AND {_NOT_OBSERVED_EXISTS} "
    f"RETURN a.id AS source_id, a.name AS source_name, 'CALLS' AS relation_type, {_CALLS_TARGET} "
    "UNION "
    "MATCH (a:Service)-[r:SENDS|RECEIVES_FROM]->(b:Queue) "
    f"WHERE {_DECLARED_EXISTS} AND {_NOT_OBSERVED_EXISTS} "
    "RETURN a.id AS source_id, a.name AS source_name, type(r) AS relation_type, "
    "b.id AS target_id, b.name AS target_name "
    "ORDER BY source_id, target_id"
)


def declared_only_relations(
    session: neo4j.Session,
    *,
    environment: str,
    since: datetime,
    until: datetime | None = None,
    qualification_enabled: bool = True,
) -> list[DeclaredOnlyRelation]:
    """O4 - Declared - Observed(window, environment) (spec §45/§38). telemetry_coverage_available
    and coverage are both composed from O5 (not duplicated Cypher), read off each row's SUBJECT -
    which is always a real, directly-identified Service, so this never needs the
    PROVIDES/target-side resolution that O1-O3's target identity does. qualification_enabled is
    spec §22's `telemetry.coverage.qualification-enabled` kill switch (11H-E/spec §11) - when
    False, `coverage` degrades to UNKNOWN for every row rather than being omitted, so API
    consumers never need to branch on the field's presence; telemetry_coverage_available's
    original boolean semantics are untouched either way."""
    rows = [
        dict(record)
        for record in session.run(_O4_QUERY, environment=environment, since=since, until=until)
    ]
    subject_ids = sorted({row["source_id"] for row in rows})
    coverage = {
        c.service_id: c
        for c in telemetry_coverage(
            session, environment=environment, since=since, service_ids=subject_ids
        )
    }
    results = []
    for row in rows:
        service_coverage = coverage.get(row["source_id"])
        if service_coverage is None:
            available = False
        elif row["relation_type"] == "CALLS":
            available = service_coverage.http_observed
        else:
            available = service_coverage.messaging_observed
        results.append(
            DeclaredOnlyRelation(
                **row,
                environment=environment,
                since=since,
                status=NOT_OBSERVED_IN_WINDOW,
                telemetry_coverage_available=available,
                coverage=_classify_coverage(
                    service_coverage,
                    row["relation_type"],
                    qualification_enabled=qualification_enabled,
                ),
            )
        )
    return results


@dataclass(frozen=True)
class ServiceTelemetryCoverage:
    """Whether a service emitted any usable telemetry at all within the window/environment (spec
    §41/§46) - used to judge how trustworthy an O4 "not observed" result is. http_observed's
    provider-side check has a known, inherited limitation: it can only see PROVIDES edges, which
    the H4 telemetry pipeline never writes for an undeclared (Fall-B) operation, so a service that
    is only ever an undeclared provider will show http_observed=False even with real observed
    traffic reaching it."""

    service_id: str
    service_name: str
    environment: str
    since: datetime
    http_observed: bool
    messaging_observed: bool
    spans_observed: bool


_ALL_SERVICES_QUERY = "MATCH (s:Service) RETURN s.id AS id, s.name AS name"

_HTTP_CALLER_OBSERVED_QUERY = (
    f"MATCH (s:Service {{id: $service_id}})-[r:CALLS]->(:Operation) WHERE {_OBSERVED_EXISTS} "
    "RETURN count(r) > 0 AS observed"
)
_HTTP_PROVIDER_OBSERVED_QUERY = (
    "MATCH (s:Service {id: $service_id})-[:PROVIDES]->(:Operation)<-[r:CALLS]-(:Service) "
    f"WHERE {_OBSERVED_EXISTS} RETURN count(r) > 0 AS observed"
)
_SENDS_OBSERVED_QUERY = (
    f"MATCH (s:Service {{id: $service_id}})-[r:SENDS]->(:Queue) WHERE {_OBSERVED_EXISTS} "
    "RETURN count(r) > 0 AS observed"
)
_RECEIVES_OBSERVED_QUERY = (
    f"MATCH (s:Service {{id: $service_id}})-[r:RECEIVES_FROM]->(:Queue) WHERE {_OBSERVED_EXISTS} "
    "RETURN count(r) > 0 AS observed"
)


def _observed(session: neo4j.Session, query: str, **params) -> bool:
    record = session.run(query, **params).single()
    return bool(record["observed"]) if record else False


def telemetry_coverage(
    session: neo4j.Session,
    *,
    environment: str,
    since: datetime,
    until: datetime | None = None,
    service_ids: list[str] | None = None,
) -> list[ServiceTelemetryCoverage]:
    """O5 - per-service telemetry coverage (spec §46). Deliberately four small separate per-service
    queries rather than one combined traversal, mirroring blast_radius.py's existing preference for
    simple per-hop queries over one clever query."""
    if service_ids is None:
        services = [(r["id"], r["name"]) for r in session.run(_ALL_SERVICES_QUERY)]
    else:
        all_names = {r["id"]: r["name"] for r in session.run(_ALL_SERVICES_QUERY)}
        services = [(sid, all_names.get(sid, sid)) for sid in service_ids]

    results = []
    for service_id, service_name in services:
        params = {
            "service_id": service_id,
            "environment": environment,
            "since": since,
            "until": until,
        }
        http_observed = _observed(session, _HTTP_CALLER_OBSERVED_QUERY, **params) or _observed(
            session, _HTTP_PROVIDER_OBSERVED_QUERY, **params
        )
        messaging_observed = _observed(session, _SENDS_OBSERVED_QUERY, **params) or _observed(
            session, _RECEIVES_OBSERVED_QUERY, **params
        )
        results.append(
            ServiceTelemetryCoverage(
                service_id=service_id,
                service_name=service_name,
                environment=environment,
                since=since,
                http_observed=http_observed,
                messaging_observed=messaging_observed,
                spans_observed=http_observed or messaging_observed,
            )
        )
    return results


def _classify_coverage(
    service_coverage: ServiceTelemetryCoverage | None,
    relation_type: str,
    *,
    qualification_enabled: bool,
) -> str:
    """Qualifies how much weight an O4 NOT_OBSERVED_IN_WINDOW finding should carry (11H R7/spec
    §11, 11H.11) - derived entirely from the O5 coverage signals already computed for this
    service/window/environment, no new Cypher. UNKNOWN when qualification is disabled (spec §22)
    or the subject has no coverage row at all (shouldn't normally happen - its own declared
    relation makes it a real Service - but is structurally the "can't assess" case either way).
    Otherwise: SUFFICIENT if the service has observed traffic of the *same* relation kind
    (CALLS -> http_observed, SENDS/RECEIVES_FROM -> messaging_observed) in this window/
    environment - a not-observed edge of a well-covered kind is meaningful evidence. PARTIAL if
    the service emits some telemetry but not of this kind (e.g. HTTP is instrumented but
    messaging isn't) - weaker evidence, since this kind simply isn't watched. NONE if the service
    emitted no usable telemetry at all in this window/environment - spec §11.1's Case B, the
    weakest possible evidence for "not observed"."""
    if not qualification_enabled or service_coverage is None:
        return COVERAGE_UNKNOWN
    relevant_observed = (
        service_coverage.http_observed
        if relation_type == "CALLS"
        else service_coverage.messaging_observed
    )
    if relevant_observed:
        return COVERAGE_SUFFICIENT
    if service_coverage.spans_observed:
        return COVERAGE_PARTIAL
    return COVERAGE_NONE


@dataclass(frozen=True)
class RuntimeRelationStatus:
    """One outgoing relation from a profiled service, labeled with its O2/O3/O4 status (used by
    service_runtime_profile - the Runtime API's per-service endpoint and the Service Explorer UI's
    Observed section, spec §49/§50)."""

    relation_type: str
    target_id: str
    target_name: str
    status: str  # "CONFIRMED" | "OBSERVED_ONLY" | NOT_OBSERVED_IN_WINDOW
    first_seen: datetime | None
    last_seen: datetime | None
    observation_count: int | None
    telemetry_coverage_available: bool | None  # only meaningful for NOT_OBSERVED_IN_WINDOW rows
    coverage: str | None  # SUFFICIENT/PARTIAL/NONE/UNKNOWN - only meaningful for the same rows


@dataclass(frozen=True)
class ServiceRuntimeProfile:
    service_id: str
    service_name: str
    environment: str
    since: datetime
    coverage: ServiceTelemetryCoverage
    relations: list[RuntimeRelationStatus]


_SERVICE_NAME_QUERY = "MATCH (s:Service {id: $id}) RETURN s.name AS name"


def service_runtime_profile(
    session: neo4j.Session,
    *,
    service_id: str,
    environment: str,
    since: datetime,
    until: datetime | None = None,
    qualification_enabled: bool = True,
) -> ServiceRuntimeProfile | None:
    """Per-service runtime view: this service's outgoing CONFIRMED + OBSERVED_ONLY + DECLARED_ONLY
    relations plus its O5 coverage (spec §49's sketch shows only outgoing declared/observed
    relations from the profiled service's own perspective - matches the existing declared
    Provides/Calls asymmetry already in service.html). Composes O2+O3+O4+O5 rather than adding a
    from_id filter to those four tested functions - filters their full-graph results down to
    source_id == service_id in Python, deliberately not touching their signatures/tests, cheap at
    this PoC's scale (same "simple over clever" call O5 itself already makes). Returns None if the
    service doesn't exist - callers decide the 404."""
    name_row = session.run(_SERVICE_NAME_QUERY, id=service_id).single()
    if name_row is None:
        return None

    confirmed = [
        r
        for r in confirmed_relations(session, environment=environment, since=since, until=until)
        if r.source_id == service_id
    ]
    observed_only = [
        r
        for r in observed_only_relations(session, environment=environment, since=since, until=until)
        if r.source_id == service_id
    ]
    declared_only = [
        r
        for r in declared_only_relations(
            session,
            environment=environment,
            since=since,
            until=until,
            qualification_enabled=qualification_enabled,
        )
        if r.source_id == service_id
    ]
    coverage = telemetry_coverage(
        session, environment=environment, since=since, until=until, service_ids=[service_id]
    )[0]

    relations = (
        [
            RuntimeRelationStatus(
                relation_type=r.relation_type,
                target_id=r.target_id,
                target_name=r.target_name,
                status="CONFIRMED",
                first_seen=r.first_seen,
                last_seen=r.last_seen,
                observation_count=r.observation_count,
                telemetry_coverage_available=None,
                coverage=None,
            )
            for r in confirmed
        ]
        + [
            RuntimeRelationStatus(
                relation_type=r.relation_type,
                target_id=r.target_id,
                target_name=r.target_name,
                status="OBSERVED_ONLY",
                first_seen=r.first_seen,
                last_seen=r.last_seen,
                observation_count=r.observation_count,
                telemetry_coverage_available=None,
                coverage=None,
            )
            for r in observed_only
        ]
        + [
            RuntimeRelationStatus(
                relation_type=r.relation_type,
                target_id=r.target_id,
                target_name=r.target_name,
                status=r.status,
                first_seen=None,
                last_seen=None,
                observation_count=None,
                telemetry_coverage_available=r.telemetry_coverage_available,
                coverage=r.coverage,
            )
            for r in declared_only
        ]
    )
    return ServiceRuntimeProfile(
        service_id=service_id,
        service_name=name_row["name"],
        environment=environment,
        since=since,
        coverage=coverage,
        relations=relations,
    )
