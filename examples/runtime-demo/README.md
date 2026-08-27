# Runtime Demo Walkthrough

This walks through the Collector-based runtime demo (H5 spec §15) end-to-end: bringing up the
stack, and then observing all three declared-vs-observed states —
[`CONFIRMED`, `OBSERVED_ONLY`, `NOT_OBSERVED_IN_WINDOW`](../../README.md#declared-vs-observed) —
plus the 11H evidence-reconciliation invariant. Steps 1-6 and 8 use `curl` against AIP's own API;
step 7 shows the same data through the web UI at <http://localhost:8000/>, including a natural
language query.

Topology (see `traffic_generator.py`'s docstring for the exact spans it sends):

```text
OrderService
   |
   +---- REST (declared + observed) ----> ProductService
   |
   +---- REST (observed only, never declared) ----> LegacyPricingService
   |
   +---- SENDS (declared + observed) ----> payment-q ----> PaymentService ----> invoice-q ----> InvoiceService
```

## 1. Prerequisites

Copy `.env.example` to `.env` at the repo root (see root `README.md`) — its `NEO4J_PASSWORD`
default is fine for this demo.

## 2. Bring up the stack

From the repo root:

```bash
docker compose -f docker-compose.demo.yml up --build
```

This starts `architecture-intelligence` (+ `neo4j`), an `otel-collector`, and the
`traffic-generator`. Leave it running in this terminal; run the commands below from a second one.
`traffic-generator` waits for `order-service` to exist as a declared Service before sending any
traffic (see its logs: `waiting for declared architecture - run curl -X POST ...`), so there's no
race with step 3 below — nothing sends until the import happens.

## 3. Import the declared architecture

```bash
curl -s -X POST http://localhost:8000/api/import | jq .
```

This loads `examples/` (OrderService/ProductService/PaymentService/InvoiceService, wired per
`examples/order-service/architecture.yaml`). `LegacyPricingService` is deliberately **not** part of
this import — it exists only as runtime traffic, never as a declaration.

## 4. NOT_OBSERVED_IN_WINDOW — check immediately, before traffic lands

Right after import, no OTLP traffic has arrived yet, so every declared relation is
`NOT_OBSERVED_IN_WINDOW` (declared, not yet seen in this window):

```bash
curl -s "http://localhost:8000/api/analysis/runtime/declared-only?environment=demo" | jq .
```

Expect `order-service`'s `CALLS -> product-service.getProduct` and `SENDS -> payment-q` (among
others) with `"status": "NOT_OBSERVED_IN_WINDOW"`. Each row also carries `coverage` — `NONE` here,
since no telemetry has arrived for these services in this environment/window yet.

## 5. CONFIRMED — wait for traffic, then re-check

The `traffic-generator` sends a batch every `TRAFFIC_INTERVAL_SECONDS` (default 5s). After ~10-15
seconds:

```bash
curl -s "http://localhost:8000/api/analysis/runtime/confirmed?environment=demo" | jq .
```

`order-service -> product-service.getProduct` and the `payment-q`/`invoice-q` sends/receives now
show up here instead — declared **and** observed. Re-running step 4's `declared-only` query now
returns an empty list for these relations (they've moved out of `NOT_OBSERVED_IN_WINDOW`).

## 6. OBSERVED_ONLY — the undocumented dependency

```bash
curl -s "http://localhost:8000/api/analysis/runtime/observed-only?environment=demo" | jq .
```

Returns `order-service -> LegacyPricingService` (via the runtime-discovered `GET /pricing/{sku}`
operation) — observed, but declared nowhere in `examples/`. This is the "most important H4
analysis" per spec §44: a real dependency the architecture manifest doesn't know about.

## 7. Using the web UI

Everything above is also visible through AIP's own minimal UI, at <http://localhost:8000/>:

- **<http://localhost:8000/services/service:order-service>** — the Service Explorer for
  `order-service`. Shows Declared and Observed side by side: `ProductService`/`payment-q` appear
  under both (that's `CONFIRMED`), and `LegacyPricingService` appears only under Observed — the
  same `OBSERVED_ONLY` finding from step 6, now visible in context rather than as a bare API
  response.
- **<http://localhost:8000/queues/queue:payment-q>** — the Queue Explorer, showing `payment-q`'s
  senders/consumers/messages.
- **<http://localhost:8000/query>** — the natural language query page. Type a question (or use one
  of these directly, e.g.
  `http://localhost:8000/query?question=Who+sends+to+payment-q%3F`):
  - `Who sends to payment-q?` — routes deterministically (no LLM needed) to A1, returning
    `OrderService`.
  - `Which dependencies are observed but undocumented?` — routes deterministically to O3, and
    returns the same `OrderService -> LegacyPricingService` finding as step 6.

  Both questions work with **no `OPENAI_API_KEY` configured** — they match the deterministic intent
  router (`app/intent/patterns.py`) directly, per spec's LLM-optional guarantee. A genuinely
  open-ended question that doesn't match a known pattern still needs an LLM provider, and returns a
  `503` explaining that rather than failing silently if one isn't configured.

  This only works out of the box because `docker-compose.demo.yml` points AIP at
  `config.demo.yaml` instead of the root `config.yaml` — the demo tags all traffic with
  `environment=demo` (`DEMO_ENVIRONMENT` in `docker-compose.demo.yml`), but the query page has no
  per-question environment override and otherwise defaults to `config.yaml`'s
  `runtime_analysis.default_environment: production`, which would silently return zero rows against
  demo data. `config.demo.yaml` is identical to `config.yaml` except that one value.

## 8. Cross-batch correlation (optional, spec §15's last paragraph)

Every 4th cycle, `traffic_generator.py` sends the OrderService/ProductService CLIENT and SERVER
spans as **two separate OTLP requests**, a few seconds apart, instead of bundled in one — well
inside the correlation buffer's default 60s TTL. Watch the container logs:

```bash
docker compose -f docker-compose.demo.yml logs -f traffic-generator
```

for the `cross-batch demo: sent CLIENT span` / `... sent matching SERVER span in a separate
request` lines. The `confirmed` query in step 5 keeps returning the same single
`order-service -> product-service.getProduct` relation either way — AIP correlates the pair across
requests rather than requiring them in the same batch.

## 9. The 11H reconciliation scenario

This is the invariant documented in [`docs/graph-model.md`](../../docs/graph-model.md): removing a
stale declaration degrades a relation from `CONFIRMED` to `OBSERVED_ONLY` — it never deletes the
relation outright, because observed evidence for it still exists.

1. Confirm the starting state — `order-service -> product-service.getProduct` should already be
   `CONFIRMED` (step 5).
2. Edit `examples/order-service/architecture.yaml` and remove (or comment out) the `calls` entry:

   ```yaml
   service: order-service
   # calls:
   #   - service: product-service
   #     operationId: getProduct
   ```

3. Re-import just `order-service` (the traffic generator keeps running, so observed evidence keeps
   accumulating throughout):

   ```bash
   curl -s -X POST http://localhost:8000/api/import/service/order-service | jq .
   ```

4. Re-check the relation:

   ```bash
   curl -s "http://localhost:8000/api/analysis/runtime/observed-only?environment=demo" | jq .
   curl -s "http://localhost:8000/api/analysis/runtime/confirmed?environment=demo" | jq .
   ```

   `order-service -> product-service.getProduct` has moved from `confirmed` into `observed-only` —
   the relation itself was never deleted, only its `DECLARED` evidence was, exactly as
   `docs/graph-model.md` describes.
5. Restore `examples/order-service/architecture.yaml` to its original contents (undo step 2) and
   re-run step 3's import to put the fixture back the way the rest of the test suite expects it.

## 10. Cleanup

```bash
docker compose -f docker-compose.demo.yml down -v
```

`-v` also drops the demo's Neo4j volumes, so the next `up` starts from an empty graph.
