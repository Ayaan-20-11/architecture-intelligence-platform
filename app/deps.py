from collections.abc import Iterator

import neo4j
from fastapi import Depends, HTTPException, Request

from app.ai.provider import LLMProvider
from app.ai.question_service import ArchitectureQuestionService
from app.graph.repository import open_session
from app.settings import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_driver(request: Request) -> neo4j.Driver:
    return request.app.state.driver


def get_read_session(request: Request) -> Iterator[neo4j.Session]:
    settings = get_settings(request)
    driver = get_driver(request)
    with open_session(driver, database=settings.config.graph.database, read_only=True) as session:
        yield session


def get_llm_provider(request: Request) -> LLMProvider:
    provider = getattr(request.app.state, "llm_provider", None)
    if provider is None:
        raise HTTPException(status_code=503, detail="LLM query subsystem is not configured")
    return provider


def build_question_service(request: Request) -> ArchitectureQuestionService | None:
    """Returns None (rather than raising) when the LLM subsystem isn't configured - for callers like the UI page that want to render a friendly message instead of a 503."""
    provider = getattr(request.app.state, "llm_provider", None)
    if provider is None:
        return None
    settings = get_settings(request)
    return ArchitectureQuestionService(
        driver=get_driver(request),
        database=settings.config.graph.database,
        provider=provider,
        max_depth=settings.config.graph.max_traversal_depth,
        max_result_rows=settings.config.llm.max_result_rows,
    )


def get_question_service(
    settings: Settings = Depends(get_settings),
    driver: neo4j.Driver = Depends(get_driver),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ArchitectureQuestionService:
    return ArchitectureQuestionService(
        driver=driver,
        database=settings.config.graph.database,
        provider=provider,
        max_depth=settings.config.graph.max_traversal_depth,
        max_result_rows=settings.config.llm.max_result_rows,
    )
