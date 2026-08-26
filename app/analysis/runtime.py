from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import neo4j

NOT_OBSERVED_IN_WINDOW = "NOT_OBSERVED_IN_WINDOW"
DEFAULT_WINDOW_HOURS = 24

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


_O4_QUERY = (
    "MATCH (a:Service)-[r:CALLS]->(o:Operation) "
    "OPTIONAL MATCH (o)<-[:PROVIDES]-(provider:Service) "
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
    session: neo4j.Session, *, environment: str, since: datetime, until: datetime | None = None
) -> list[DeclaredOnlyRelation]:
    """O4 - Declared - Observed(window, environment) (spec §45/§38). telemetry_coverage_available
    is composed from O5 (not duplicated Cypher), read off each row's SUBJECT - which is always a
    real, directly-identified Service, so this never needs the PROVIDES/target-side resolution
    that O1-O3's target identity does."""
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
