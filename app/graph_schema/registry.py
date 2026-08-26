from app.graph_schema.model import RelationDefinition

RELATIONS: dict[str, RelationDefinition] = {
    "PROVIDES": RelationDefinition(
        name="PROVIDES",
        source_labels=frozenset({"Service"}),
        target_labels=frozenset({"Operation"}),
    ),
    "CALLS": RelationDefinition(
        name="CALLS",
        source_labels=frozenset({"Service"}),
        target_labels=frozenset({"Operation"}),
    ),
    "REQUEST_SCHEMA": RelationDefinition(
        name="REQUEST_SCHEMA",
        source_labels=frozenset({"Operation"}),
        target_labels=frozenset({"Schema"}),
    ),
    "RESPONSE_SCHEMA": RelationDefinition(
        name="RESPONSE_SCHEMA",
        source_labels=frozenset({"Operation"}),
        target_labels=frozenset({"Schema"}),
    ),
    "SENDS": RelationDefinition(
        name="SENDS",
        source_labels=frozenset({"Service"}),
        target_labels=frozenset({"Queue"}),
    ),
    "RECEIVES_FROM": RelationDefinition(
        name="RECEIVES_FROM",
        source_labels=frozenset({"Service"}),
        target_labels=frozenset({"Queue"}),
    ),
    "CARRIES": RelationDefinition(
        name="CARRIES",
        source_labels=frozenset({"Queue"}),
        target_labels=frozenset({"Message"}),
    ),
    "CONFORMS_TO": RelationDefinition(
        name="CONFORMS_TO",
        source_labels=frozenset({"Message"}),
        target_labels=frozenset({"Schema"}),
    ),
    "DEAD_LETTERS_TO": RelationDefinition(
        name="DEAD_LETTERS_TO",
        source_labels=frozenset({"Queue"}),
        target_labels=frozenset({"Queue"}),
    ),
}
