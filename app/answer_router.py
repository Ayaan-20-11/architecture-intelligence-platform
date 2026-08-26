from dataclasses import dataclass
from typing import Literal

import neo4j

from app.ai.question_service import ArchitectureQuestionService
from app.analysis import registry
from app.intent.entity_resolver import fetch_candidates
from app.intent.model import ArchitectureIntent
from app.intent.router import classify


class LLMNotConfiguredError(RuntimeError):
    """Raised when a question is UNKNOWN (must fall back to the LLM) but no LLM provider is
    configured. Deterministic questions never raise this - they don't need a provider at all."""


@dataclass(frozen=True)
class RoutedAnswer:
    question: str
    execution_mode: Literal["DETERMINISTIC", "LLM"]
    intent: str | None
    cypher: str | None
    rows: list[dict]
    answer: str


def answer_question(
    *,
    session: neo4j.Session,
    question: str,
    deterministic_threshold: float,
    question_service: ArchitectureQuestionService | None,
) -> RoutedAnswer:
    """Entry point for both the JSON API and the UI query page (spec §6.3/§9): known-intent
    questions are answered by an existing tested analysis, bypassing LLM Cypher generation
    entirely (AC-H3-3); only UNKNOWN questions fall back to the (H1/H2-hardened) LLM path, which
    stays untouched by this module."""
    candidates = {
        "Service": fetch_candidates(session, "Service"),
        "Queue": fetch_candidates(session, "Queue"),
    }
    intent_result = classify(question, candidates=candidates, threshold=deterministic_threshold)

    if intent_result.intent is not ArchitectureIntent.UNKNOWN:
        rows = registry.execute(session, intent_result.intent, intent_result.parameters)
        return RoutedAnswer(
            question=question,
            execution_mode="DETERMINISTIC",
            intent=intent_result.intent.value,
            cypher=None,
            rows=rows,
            answer=f"Found {len(rows)} row(s).",
        )

    if question_service is None:
        raise LLMNotConfiguredError()

    result = question_service.ask(question)
    return RoutedAnswer(
        question=result.question,
        execution_mode="LLM",
        intent=None,
        cypher=result.cypher,
        rows=result.rows,
        answer=result.answer,
    )
