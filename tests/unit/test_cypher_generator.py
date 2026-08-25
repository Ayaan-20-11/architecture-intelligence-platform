from app.ai.cypher_generator import GRAPH_SCHEMA_DESCRIPTION, generate_cypher


class FakeProvider:
    def __init__(self, cypher: str = "MATCH (n) RETURN n"):
        self.cypher = cypher
        self.calls: list[dict] = []

    def generate_cypher(self, *, question: str, schema_description: str) -> str:
        self.calls.append({"question": question, "schema_description": schema_description})
        return self.cypher

    def compose_answer(self, *, question: str, cypher: str, rows: list[dict]) -> str:
        raise NotImplementedError


def test_generate_cypher_passes_question_and_fixed_schema_to_provider():
    provider = FakeProvider(cypher="MATCH (s:Service) RETURN s.id LIMIT 100")
    result = generate_cypher(provider, "who sends payment-q?")

    assert result == "MATCH (s:Service) RETURN s.id LIMIT 100"
    assert len(provider.calls) == 1
    assert provider.calls[0]["question"] == "who sends payment-q?"
    assert provider.calls[0]["schema_description"] == GRAPH_SCHEMA_DESCRIPTION


def test_schema_description_documents_all_node_labels_and_relations():
    for label in ("Service", "Operation", "Queue", "Message", "Schema"):
        assert label in GRAPH_SCHEMA_DESCRIPTION
    for relation in (
        "PROVIDES",
        "CALLS",
        "REQUEST_SCHEMA",
        "RESPONSE_SCHEMA",
        "SENDS",
        "RECEIVES_FROM",
        "CARRIES",
        "CONFORMS_TO",
        "DEAD_LETTERS_TO",
    ):
        assert relation in GRAPH_SCHEMA_DESCRIPTION
