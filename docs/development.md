# Development

```bash
uv sync                                # install dependencies
uv run pytest tests/unit               # fast unit tests (no Neo4j needed)
uv run pytest tests/integration        # Testcontainers-backed tests (needs Docker)
uv run ruff check .                    # lint
uv run ruff format .                   # format
```

Copy `.env.example` to `.env` and fill in `NEO4J_PASSWORD` (and `OPENAI_API_KEY` if you want the
natural-language query layer — the LLM query subsystem is fully optional and disables itself with a
friendly `503` if unset; see [`configuration.md`](configuration.md)). To run the app locally against
a Neo4j you start yourself:

```bash
export NEO4J_PASSWORD=devpassword     # and NEO4J_USER/OPENAI_API_KEY as needed
uv run uvicorn app.main:app --reload
```

`config.yaml` points `sources.directories` at `examples/`, so `POST /api/import` works out of the
box against this repo's fixture services. Or run the full stack via Docker Compose:

```bash
docker compose up
```

For the OpenTelemetry Collector-based runtime demo, see the README's "Runtime telemetry" section
and [`opentelemetry.md`](opentelemetry.md).

## Test layout

- `tests/unit/` — no external dependencies; runs in a couple of seconds.
- `tests/integration/` — Testcontainers-backed against a real Neo4j; each test module owns its own
  module-scoped container.
- `tests/fixtures/` — shared synthetic fixture data used across both.
- `examples/` — the reference test-fixture landscape used across unit/integration tests and the
  local Quick Start (`order-service` calls `product-service` and sends to `payment-q`;
  `product-service` only provides `getProduct`; `payment-service` receives `payment-q` and sends
  `invoice-q`; `invoice-service` only receives `invoice-q`; `unused-q`/`unknown-producer-q` exist
  specifically to exercise the A3/A4 orphan-queue analyses).

## Adding a new source of declared or observed architecture

See [`adapter-development.md`](adapter-development.md) for the extension point a new adapter needs
to fit — what it must produce (an `ArchitectureModel` for a declared source, an `ObservationBatch`
for a runtime source) rather than a specific class hierarchy to inherit from.

## Contributing

A dedicated `CONTRIBUTING.md` with the full contribution workflow is planned but not yet published.
Until then, open an issue or pull request as usual, and see
[`security-model.md`](security-model.md) if your change touches the LLM layer, the OpenTelemetry
ingestion path, or the correlation buffer — those three have explicit trust-boundary rules any
change there must preserve.
