from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/query", tags=["query"])


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    question: str
    cypher: str | None = None
    rows: list[dict] = []
    answer: str


@router.post("")
def post_query(request: QueryRequest) -> QueryResponse:
    """POST /api/query stub (spec §14) - wired to the real AI subsystem in Iteration 8."""
    return QueryResponse(
        question=request.question,
        cypher=None,
        rows=[],
        answer="Natural language query is not implemented yet (Iteration 8).",
    )
