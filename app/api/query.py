from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.ai.question_service import ArchitectureQuestionService
from app.deps import get_question_service

router = APIRouter(prefix="/api/query", tags=["query"])


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    question: str
    cypher: str | None = None
    rows: list[dict] = []
    answer: str


@router.post("")
def post_query(
    request: QueryRequest, service: ArchitectureQuestionService = Depends(get_question_service)
) -> QueryResponse:
    """POST /api/query: natural-language question -> validated read-only Cypher -> answer (spec §14/§15)."""
    result = service.ask(request.question)
    return QueryResponse(
        question=result.question, cypher=result.cypher, rows=result.rows, answer=result.answer
    )
