from collections.abc import Callable, Iterable
from dataclasses import dataclass

import neo4j

DEFAULT_MAX_DEPTH = 5

_NEIGHBORS_QUERY = (
    "MATCH (:Service {id: $service_id})-[:CALLS]->(:Operation)<-[:PROVIDES]-(b:Service) "
    "RETURN DISTINCT b.id AS id, b.name AS name, 'SYNC' AS via "
    "UNION "
    "MATCH (:Service {id: $service_id})-[:SENDS]->(:Queue)<-[:RECEIVES_FROM]-(b:Service) "
    "RETURN DISTINCT b.id AS id, b.name AS name, 'ASYNC' AS via "
    "ORDER BY id, via"
)


@dataclass(frozen=True)
class BlastRadiusEntry:
    service_id: str
    service_name: str
    depth: int
    via: str


Neighbor = tuple[str, str, str]


def _traverse(
    fetch_neighbors: Callable[[str], Iterable[Neighbor]], service_id: str, *, max_depth: int
) -> list[BlastRadiusEntry]:
    visited = {service_id}
    frontier = [service_id]
    results: list[BlastRadiusEntry] = []

    depth = 0
    while frontier and depth < max_depth:
        depth += 1
        next_frontier: list[str] = []
        for current_id in frontier:
            for neighbor_id, neighbor_name, via in fetch_neighbors(current_id):
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                results.append(BlastRadiusEntry(neighbor_id, neighbor_name, depth, via))
                next_frontier.append(neighbor_id)
        frontier = next_frontier

    return results


def _fetch_neighbors(session: neo4j.Session, service_id: str) -> list[Neighbor]:
    return [
        (record["id"], record["name"], record["via"])
        for record in session.run(_NEIGHBORS_QUERY, service_id=service_id)
    ]


def blast_radius(
    session: neo4j.Session, service_id: str, *, max_depth: int = DEFAULT_MAX_DEPTH
) -> list[BlastRadiusEntry]:
    """A5 - mixed sync+async blast radius (spec §13.5), BFS in Python since vanilla Neo4j has no APOC for multi-pattern variable-length traversal."""
    return _traverse(lambda sid: _fetch_neighbors(session, sid), service_id, max_depth=max_depth)
