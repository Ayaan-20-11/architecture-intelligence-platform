from pydantic import BaseModel


class RelationDefinition(BaseModel):
    """Domain/range for a graph relationship type (spec §5.3): which node labels are valid
    as the source and target of a relationship of this type."""

    name: str
    source_labels: frozenset[str]
    target_labels: frozenset[str]
