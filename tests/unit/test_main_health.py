from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import AppConfig, Secrets, Settings


def _build_app():
    app = create_app()
    app.state.driver = None
    app.state.settings = Settings(
        config=AppConfig(), secrets=Secrets(neo4j_user="unused", neo4j_password="unused")
    )
    return app


client = TestClient(_build_app(), raise_server_exceptions=False)


def test_health_neo4j_failure_never_leaks_exception_detail():
    """CodeQL py/stack-trace-exposure regression test - a Neo4j failure must be logged
    server-side only, never returned in the response body to an unauthenticated caller
    (app/main.py's health_neo4j handler; app.state.driver = None forces the same
    AttributeError-on-.session() failure a real unreachable Neo4j would raise)."""
    response = client.get("/health/neo4j")
    assert response.status_code == 503
    assert response.json() == {"status": "error"}
