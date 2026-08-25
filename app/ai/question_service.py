from dataclasses import dataclass

import neo4j

from app.ai.answer_composer import compose_answer
from app.ai.cypher_generator import generate_cypher
from app.ai.cypher_validator import DEFAULT_MAX_DEPTH, DEFAULT_MAX_RESULT_ROWS, validate_cypher
from app.ai.provider import LLMProvider
from app.graph.repository import open_session


@dataclass(frozen=True)
class AnswerResult:
    question: str
    cypher: str
    rows: list[dict]
    answer: str


class ArchitectureQuestionService:
    """Orchestrates generate -> validate -> read-only execute -> compose (spec §15)."""

    def __init__(
        self,
        *,
        driver: neo4j.Driver,
        database: str,
        provider: LLMProvider,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_result_rows: int = DEFAULT_MAX_RESULT_ROWS,
    ):
        self._driver = driver
        self._database = database
        self._provider = provider
        self._max_depth = max_depth
        self._max_result_rows = max_result_rows

    def ask(self, question: str) -> AnswerResult:
        candidate_cypher = generate_cypher(self._provider, question)
        cypher = validate_cypher(
            candidate_cypher, max_depth=self._max_depth, max_result_rows=self._max_result_rows
        )

        with open_session(self._driver, database=self._database, read_only=True) as session:
            rows = [record.data() for record in session.run(cypher)]

        answer = compose_answer(self._provider, question=question, cypher=cypher, rows=rows)
        return AnswerResult(question=question, cypher=cypher, rows=rows, answer=answer)
