from dataclasses import dataclass

import neo4j


@dataclass(frozen=True)
class DependencyEdge:
    source_id: str
    source_name: str
    target_id: str
    target_name: str


_SYNC_DEPENDS_ON_QUERY = (
    "MATCH (a:Service)-[:CALLS]->(:Operation)<-[:PROVIDES]-(b:Service) "
    "RETURN DISTINCT a.id AS source_id, a.name AS source_name, b.id AS target_id, b.name AS target_name "
    "ORDER BY source_id, target_id"
)

_ASYNC_FLOW_TO_QUERY = (
    "MATCH (a:Service)-[:SENDS]->(:Queue)<-[:RECEIVES_FROM]-(b:Service) "
    "RETURN DISTINCT a.id AS source_id, a.name AS source_name, b.id AS target_id, b.name AS target_name "
    "ORDER BY source_id, target_id"
)


def sync_depends_on(session: neo4j.Session) -> list[DependencyEdge]:
    """Computed view: SYNC_DEPENDS_ON, A -[:CALLS]-> Operation <-[:PROVIDES]- B (spec §13.6). Not materialized."""
    return [DependencyEdge(**record.data()) for record in session.run(_SYNC_DEPENDS_ON_QUERY)]


def async_flow_to(session: neo4j.Session) -> list[DependencyEdge]:
    """Computed view: ASYNC_FLOW_TO, A -[:SENDS]-> Queue <-[:RECEIVES_FROM]- B (spec §13.6). Not materialized."""
    return [DependencyEdge(**record.data()) for record in session.run(_ASYNC_FLOW_TO_QUERY)]
