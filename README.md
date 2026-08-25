# Architecture Intelligence Platform — PoC

Proves that an Architecture Knowledge Graph can be built automatically from existing OpenAPI and
AsyncAPI specifications, unifying synchronous REST communication and asynchronous queue communication
in one Neo4j-backed model, with deterministic Cypher analyses and a read-only LLM query layer on top.

- Full design: `Architecture_Intelligence_Platform_PoC_Specification_Python.pdf`
- Engineering task breakdown: `IMPLEMENTATION_PLAN.md`
- Guidance for AI coding agents working in this repo: `CLAUDE.md`

## Status

Through Iteration 8 of `IMPLEMENTATION_PLAN.md`: canonical model, OpenAPI/AsyncAPI/manifest adapters,
ingestion pipeline + validation, Neo4j importer, the five standard analyses, a FastAPI app with a
minimal server-rendered UI, and the LLM query subsystem (OpenAI-backed).

## Development

```bash
uv sync                                # install dependencies
uv run pytest tests/unit               # fast unit tests (no Neo4j needed)
uv run pytest tests/integration        # Testcontainers-backed tests (needs Docker)
uv run ruff check .                    # lint
uv run ruff format .                   # format
```

Copy `.env.example` to `.env` and fill in `NEO4J_PASSWORD` and `OPENAI_API_KEY` (the LLM query
subsystem is disabled with a friendly message if `OPENAI_API_KEY` is unset). To run the app locally
against a Neo4j you start yourself:

```bash
export NEO4J_PASSWORD=devpassword     # and NEO4J_USER/OPENAI_API_KEY as needed
uv run uvicorn app.main:app --reload
```

`config.yaml` (spec §17.1 shape) points `sources.directories` at `examples/`, so `POST /api/import`
works out of the box against this repo's fixture services. Or run the full stack via Docker Compose:

```bash
docker compose up
```
