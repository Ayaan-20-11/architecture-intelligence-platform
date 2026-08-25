import neo4j

CONSTRAINTS = [
    "CREATE CONSTRAINT service_id IF NOT EXISTS FOR (s:Service) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT operation_id IF NOT EXISTS FOR (o:Operation) REQUIRE o.id IS UNIQUE",
    "CREATE CONSTRAINT queue_id IF NOT EXISTS FOR (q:Queue) REQUIRE q.id IS UNIQUE",
    "CREATE CONSTRAINT message_id IF NOT EXISTS FOR (m:Message) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT schema_id IF NOT EXISTS FOR (s:Schema) REQUIRE s.id IS UNIQUE",
]


def ensure_schema(session: neo4j.Session) -> None:
    """Applies the spec §11.4 uniqueness constraints idempotently."""
    for statement in CONSTRAINTS:
        session.run(statement)
