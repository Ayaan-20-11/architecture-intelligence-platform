import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from app.ai.provider import OpenAIProvider
from app.ai.semantic_query_validator import SemanticValidationError
from app.api import analysis, evidence, import_api, messages, query, queues, services, ui
from app.deps import get_driver, get_settings
from app.graph.repository import build_driver, open_session
from app.settings import Settings, load_settings

CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", "config.yaml"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings(CONFIG_PATH)
    app.state.settings = settings
    app.state.driver = build_driver(
        settings.config.graph.uri, settings.secrets.neo4j_user, settings.secrets.neo4j_password
    )
    if settings.config.llm.enabled and settings.secrets.openai_api_key:
        app.state.llm_provider = OpenAIProvider(api_key=settings.secrets.openai_api_key)
    else:
        app.state.llm_provider = None
    yield
    app.state.driver.close()


def create_app() -> FastAPI:
    """Builds the FastAPI app without touching env vars/Neo4j - real settings/driver only load on lifespan startup."""
    app = FastAPI(title="Architecture Intelligence PoC", lifespan=lifespan)

    app.include_router(services.router)
    app.include_router(queues.router)
    app.include_router(messages.router)
    app.include_router(analysis.router)
    app.include_router(import_api.router)
    app.include_router(query.router)
    app.include_router(evidence.router)
    app.include_router(ui.router)

    @app.exception_handler(SemanticValidationError)
    def handle_semantic_validation_error(request: Request, exc: SemanticValidationError):
        """Spec §5.10: structurally invalid generated Cypher (e.g. wrong relationship direction)
        never reaches Neo4j and is reported as 422 with the violated relation's domain/range."""
        return JSONResponse(
            status_code=422,
            content={
                "code": "SEMANTIC_QUERY_INVALID",
                "message": str(exc),
                "relation": exc.relation,
                "expectedSource": sorted(exc.expected_source),
                "expectedTarget": sorted(exc.expected_target),
            },
        )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/health/neo4j")
    def health_neo4j(settings: Settings = Depends(get_settings), driver=Depends(get_driver)):
        try:
            with open_session(
                driver, database=settings.config.graph.database, read_only=True
            ) as session:
                session.run("RETURN 1").consume()
        except Exception as exc:  # noqa: BLE001 - health check must report any failure, not just specific ones
            return JSONResponse(status_code=503, content={"status": "error", "detail": str(exc)})
        return {"status": "ok"}

    return app


app = create_app()
