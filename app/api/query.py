from typing import Literal

import neo4j
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.ai.question_service import ArchitectureQuestionService
from app.answer_router import LLMNotConfiguredError, answer_question
from app.deps import build_question_service, get_read_session, get_settings
from app.settings import Settings

router = APIRouter(prefix="/api/query", tags=["query"])


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    question: str
    cypher: str | None = None
    rows: list[dict] = []
    answer: str
    execution_mode: Literal["DETERMINISTIC", "LLM"] = "LLM"
    intent: str | None = None


@router.post("")
def post_query(
    request: QueryRequest,
    session: neo4j.Session = Depends(get_read_session),
    settings: Settings = Depends(get_settings),
    question_service: ArchitectureQuestionService | None = Depends(build_question_service),
) -> QueryResponse:
    """POST /api/query: a known-intent question is answered by an existing deterministic analysis
    (spec §6); only an unrecognized question falls back to validated read-only LLM-generated
    Cypher (spec §14/§15)."""
    try:
        routed = answer_question(
            session=session,
            question=request.question,
            deterministic_threshold=settings.config.intent_router.deterministic_threshold,
            question_service=question_service,
        )
    except LLMNotConfiguredError as exc:
        raise HTTPException(
            status_code=503, detail="LLM query subsystem is not configured"
        ) from exc
    return QueryResponse(
        question=routed.question,
        cypher=routed.cypher,
        rows=routed.rows,
        answer=routed.answer,
        execution_mode=routed.execution_mode,
        intent=routed.intent,
    )
