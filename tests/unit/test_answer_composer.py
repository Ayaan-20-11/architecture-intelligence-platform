from app.ai.answer_composer import compose_answer


class FakeProvider:
    def __init__(self, answer: str = "the answer"):
        self.answer = answer
        self.calls: list[dict] = []

    def generate_cypher(self, *, question: str, schema_description: str) -> str:
        raise NotImplementedError

    def compose_answer(self, *, question: str, cypher: str, rows: list[dict]) -> str:
        self.calls.append({"question": question, "cypher": cypher, "rows": rows})
        return self.answer


def test_empty_rows_short_circuits_without_calling_the_provider():
    provider = FakeProvider()
    result = compose_answer(
        provider, question="who sends payment-q?", cypher="MATCH (n) RETURN n", rows=[]
    )

    assert "no matching data" in result.lower()
    assert provider.calls == []


def test_nonempty_rows_delegates_to_provider_with_full_context():
    provider = FakeProvider(answer="OrderService sends payment-q.")
    rows = [{"id": "service:order-service", "name": "OrderService"}]

    result = compose_answer(
        provider,
        question="who sends payment-q?",
        cypher="MATCH (s)-[:SENDS]->(q) RETURN s",
        rows=rows,
    )

    assert result == "OrderService sends payment-q."
    assert len(provider.calls) == 1
    assert provider.calls[0]["question"] == "who sends payment-q?"
    assert provider.calls[0]["cypher"] == "MATCH (s)-[:SENDS]->(q) RETURN s"
    assert provider.calls[0]["rows"] == rows
