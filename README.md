# Architecture Intelligence Platform — PoC

Proves that an Architecture Knowledge Graph can be built automatically from existing OpenAPI and
AsyncAPI specifications, unifying synchronous REST communication and asynchronous queue communication
in one Neo4j-backed model, with deterministic Cypher analyses and a read-only LLM query layer on top.

- Full design: `Architecture_Intelligence_Platform_PoC_Specification_Python.pdf`
- Engineering task breakdown: `IMPLEMENTATION_PLAN.md`
- Guidance for AI coding agents working in this repo: `CLAUDE.md`

## Status

Greenfield / early bootstrapping (Iteration 0 of `IMPLEMENTATION_PLAN.md`). No application code yet.

## Development

```bash
uv sync                        # install dependencies
uv run pytest                  # run tests (once they exist)
uv run ruff check .            # lint
uv run uvicorn app.main:app --reload   # run the API locally (once app/main.py exists)
```

Copy `.env.example` to `.env` and fill in `NEO4J_PASSWORD` and `ANTHROPIC_API_KEY` before running against
Docker Compose:

```bash
docker compose up
```
