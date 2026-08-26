import re
from dataclasses import dataclass

import neo4j

from app.canonical import ids
from app.telemetry.model import DiscoveryStatus, RuntimeSpan

_CANDIDATES_QUERY = "MATCH (s:Service) RETURN s.id AS id, s.name AS name, s.namespace AS namespace"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class DeclaredServiceCandidate:
    id: str
    name: str
    namespace: str | None


@dataclass(frozen=True)
class ServiceResolution:
    service_id: str
    discovery_status: DiscoveryStatus


@dataclass(frozen=True)
class ResolvedObservation:
    service_id: str
    discovery_status: DiscoveryStatus
    environment: str | None


def _slugify(name: str) -> str:
    return _SLUG_RE.sub("-", name.lower()).strip("-")


def resolve_service(
    candidates: list[DeclaredServiceCandidate],
    *,
    service_name: str,
    service_namespace: str | None,
    aliases: dict[str, str],
) -> ServiceResolution:
    """Matches an observed service identity against declared Services (spec §12). Exact-match
    only - OTel's service.name/service.namespace are structured attributes, not free-text human
    phrasing, so no normalization/substring fuzziness is applied (contrast
    app.intent.entity_resolver, which does need that for NL questions)."""
    # Tier 1: namespace + name.
    if service_namespace is not None:
        tier1 = [
            c for c in candidates if c.namespace == service_namespace and c.name == service_name
        ]
        if len(tier1) == 1:
            return ServiceResolution(tier1[0].id, DiscoveryStatus.DECLARED)

    # Tier 2: name alone - only if it uniquely identifies one declared service. Two declared
    # services can plausibly share a display name (id comes from a slug, name from free-text
    # document metadata) - don't guess if that happens.
    tier2 = [c for c in candidates if c.name == service_name]
    if len(tier2) == 1:
        return ServiceResolution(tier2[0].id, DiscoveryStatus.DECLARED)

    # Tier 3: configured alias.
    if service_name in aliases:
        return ServiceResolution(aliases[service_name], DiscoveryStatus.DECLARED)

    # Tier 4: observed-only - mint a deterministic id (spec §13).
    minted_id = ids.service_id(_slugify(service_name), namespace=service_namespace)
    return ServiceResolution(minted_id, DiscoveryStatus.OBSERVED_ONLY)


def resolve_runtime_span(
    candidates: list[DeclaredServiceCandidate],
    span: RuntimeSpan,
    *,
    aliases: dict[str, str],
) -> ResolvedObservation:
    """Resolves a RuntimeSpan's service identity and carries its environment along (spec §14) -
    Services themselves stay environment-agnostic; only the observation is environment-tagged."""
    resolution = resolve_service(
        candidates,
        service_name=span.service_name,
        service_namespace=span.service_namespace,
        aliases=aliases,
    )
    return ResolvedObservation(
        service_id=resolution.service_id,
        discovery_status=resolution.discovery_status,
        environment=span.environment,
    )


def fetch_candidates(session: neo4j.Session) -> list[DeclaredServiceCandidate]:
    return [
        DeclaredServiceCandidate(record["id"], record["name"], record["namespace"])
        for record in session.run(_CANDIDATES_QUERY)
    ]
