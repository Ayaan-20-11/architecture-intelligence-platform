from app.ai.provider import LLMProvider

_NO_RESULTS_ANSWER = "The graph has no matching data for this question."


def compose_answer(provider: LLMProvider, *, question: str, cypher: str, rows: list[dict]) -> str:
    """Builds the answer strictly from result rows (spec §15.1/§9) - never invents facts beyond them."""
    if not rows:
        return _NO_RESULTS_ANSWER
    return provider.compose_answer(question=question, cypher=cypher, rows=rows)
