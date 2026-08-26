from dataclasses import dataclass

import neo4j

from app.canonical import ids
from app.telemetry.model import DiscoveryStatus

_CANDIDATES_QUERY = "MATCH (q:Queue) RETURN q.id AS id, q.name AS name, q.namespace AS namespace"


@dataclass(frozen=True)
class DeclaredQueueCandidate:
    id: str
    name: str
    namespace: str | None


@dataclass(frozen=True)
class QueueResolution:
    queue_id: str
    discovery_status: DiscoveryStatus


def resolve_queue(
    candidates: list[DeclaredQueueCandidate],
    *,
    messaging_system: str | None,
    destination_name: str,
    aliases: dict[str, str],
) -> QueueResolution:
    """Matches an observed messaging destination against declared AsyncAPI queues (spec §27/§28).
    Exact match only, mirroring resolve_service's tiering: messaging.system+destination_name is a
    real match tier but is dormant against today's data (no declared Queue carries a namespace -
    see app/ingestion/asyncapi_adapter.py's unused x-namespace extension); bare destination_name is
    what actually unifies AsyncAPI-declared and OTel-observed queues today (spec §27's "must not
    create two parallel nodes" goal), since real declared Queue.name values match OTel
    messaging.destination.name values directly."""
    if messaging_system is not None:
        system_matches = [
            c for c in candidates if c.namespace == messaging_system and c.name == destination_name
        ]
        if len(system_matches) == 1:
            return QueueResolution(system_matches[0].id, DiscoveryStatus.DECLARED)

    name_matches = [c for c in candidates if c.name == destination_name]
    if len(name_matches) == 1:
        return QueueResolution(name_matches[0].id, DiscoveryStatus.DECLARED)

    if destination_name in aliases:
        return QueueResolution(aliases[destination_name], DiscoveryStatus.DECLARED)

    minted_id = ids.queue_id(destination_name, namespace=messaging_system)
    return QueueResolution(minted_id, DiscoveryStatus.OBSERVED_ONLY)


def fetch_queue_candidates(session: neo4j.Session) -> list[DeclaredQueueCandidate]:
    return [
        DeclaredQueueCandidate(id=record["id"], name=record["name"], namespace=record["namespace"])
        for record in session.run(_CANDIDATES_QUERY)
    ]
