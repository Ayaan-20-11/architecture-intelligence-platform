# Analyses

All analyses run as fixed, parameterized Cypher queries — no LLM involved anywhere in this list.
The LLM's only job (see [`semantic-validation.md`](semantic-validation.md)) is routing a
natural-language question to one of these when possible, and falling back to validated, read-only
generated Cypher only when it can't.

## Deterministic architecture analyses (A1-A5)

Declared-architecture analyses over `app/analysis/queues.py`/`blast_radius.py`:

| | Endpoint | Function | Answers |
|---|---|---|---|
| A1 | `GET /api/analysis/queues/{id}/senders` | `senders_of_queue` | Who sends to this queue? |
| A2 | `GET /api/analysis/queues/{id}/consumers` | `consumers_of_queue` | Who consumes this queue? |
| A3 | `GET /api/analysis/queues/without-consumers` | `queues_without_consumers` | Queues with a sender but no known consumer |
| A4 | `GET /api/analysis/queues/without-senders` | `queues_without_senders` | Queues with a consumer but no known sender |
| A5 | `GET /api/analysis/services/{id}/blast-radius` | `blast_radius` | Mixed-architecture impact analysis — traverses both sync (`CALLS`/`PROVIDES`) and async (`SENDS`/`RECEIVES_FROM`) edges, default max depth 5 (`DEFAULT_MAX_DEPTH`, configurable per-request via `?depth=`) |

`app/analysis/dependencies.py` additionally computes the two derived, never-materialized dependency
views mentioned in [`graph-model.md`](graph-model.md): `sync_depends_on` and `async_flow_to`.

## Runtime analyses (O1-O5)

Declared-vs-observed analyses over `app/analysis/runtime.py`, every one scoped to an `environment`
and a `since`/`until` time window:

| | Endpoint | Function | Answers |
|---|---|---|---|
| O1 | `GET /api/runtime/relations` | `observed_relations` | Everything actually observed at runtime, with aggregation and optional filters — no declared/observed comparison, just raw observation |
| O2 | `GET /api/analysis/runtime/confirmed` | `confirmed_relations` | Declared **and** observed — `CONFIRMED` |
| O3 | `GET /api/analysis/runtime/observed-only` | `observed_only_relations` | Observed but never declared — undocumented real dependencies; the spec calls this "probably the most important" runtime analysis |
| O4 | `GET /api/analysis/runtime/declared-only` | `declared_only_relations` | Declared but not observed in this window — `NOT_OBSERVED_IN_WINDOW`, qualified by a coverage classification (see [`opentelemetry.md`](opentelemetry.md)) |
| O5 | `GET /api/analysis/runtime/coverage` | `telemetry_coverage` | Per-service telemetry coverage (`http_observed`/`messaging_observed`/`spans_observed`) — used to judge how much weight an O4 finding should carry |

`GET /api/runtime/services/{id}` (`service_runtime_profile`) composes O2+O3+O4+O5 into one
per-service view — this is what powers the Service Explorer UI's "Observed" section.

## Natural-language routing

`app/analysis/registry.py`'s `INTENT_HANDLERS` maps each recognized intent (A1-A5, O1-O5) straight
to the function above — a deterministically-routed question calls the exact same code as its REST
endpoint, so a natural-language answer and its equivalent direct API call are guaranteed to agree.
