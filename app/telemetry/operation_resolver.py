from dataclasses import dataclass

import neo4j

from app.canonical import ids
from app.telemetry.model import DiscoveryStatus

_CANDIDATES_QUERY = (
    "MATCH (s:Service)-[:PROVIDES]->(o:Operation) "
    # 11H-D: an OBSERVED_ONLY operation now also gets a PROVIDES edge (its provider is
    # observed-confirmable), but its Operation node is only ever MERGEd via the stub-entity path
    # (id/name/discovery_status), never carrying real method/path properties - only a genuinely
    # DECLARED operation (written by the OpenAPI adapter's node import) has both set. Excluding
    # null-method/path candidates here keeps Fall-A matching scoped to real declared operations,
    # as it always implicitly was before OBSERVED_ONLY operations could reach this query at all.
    "WHERE o.method IS NOT NULL AND o.path IS NOT NULL "
    "RETURN s.id AS provider_service_id, o.id AS id, o.method AS method, o.path AS path"
)


@dataclass(frozen=True)
class DeclaredOperationCandidate:
    id: str
    provider_service_id: str
    method: str
    path: str


@dataclass(frozen=True)
class OperationResolution:
    operation_id: str | None
    discovery_status: DiscoveryStatus | None


def resolve_operation(
    candidates: list[DeclaredOperationCandidate],
    *,
    provider_service_id: str,
    method: str,
    route: str | None,
) -> OperationResolution:
    """Matches an observed HTTP operation against declared OpenAPI operations (spec §22/§23).
    Exact match only - http.route/url.template are structured attributes, not free text. A missing
    route (Fall C) is UNRESOLVED - it must never become a graph node, or /products/4711,
    /products/4712, ... would each mint a distinct Operation."""
    if not route:
        return OperationResolution(None, None)  # Fall C

    normalized_method = method.upper()
    for candidate in candidates:
        if (
            candidate.provider_service_id == provider_service_id
            and candidate.method.upper() == normalized_method
            and candidate.path == route
        ):
            return OperationResolution(candidate.id, DiscoveryStatus.DECLARED)  # Fall A

    # Fall B: observed-only. Reuses the same formatter declared operations use, passing the full
    # provider_service_id (not a bare slug, which service_resolver never exposes) - the resulting
    # id is visually distinct from a declared operation id as a side effect, not by special-casing.
    minted_id = ids.operation_id(provider_service_id, normalized_method, route)
    return OperationResolution(minted_id, DiscoveryStatus.OBSERVED_ONLY)


def fetch_operation_candidates(session: neo4j.Session) -> list[DeclaredOperationCandidate]:
    return [
        DeclaredOperationCandidate(
            id=record["id"],
            provider_service_id=record["provider_service_id"],
            method=record["method"],
            path=record["path"],
        )
        for record in session.run(_CANDIDATES_QUERY)
    ]
