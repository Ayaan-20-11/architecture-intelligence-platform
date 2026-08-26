# Graph Model

## Node labels

`Service`, `Operation`, `Queue`, `Message`, `Schema`, `Evidence` — each with a Neo4j uniqueness
constraint on `id` (`app/graph/schema.py`).

## Relations

| Relation | From -> To | Meaning |
|---|---|---|
| `PROVIDES` | Service -> Operation | REST provider |
| `CALLS` | Service -> Operation | REST caller |
| `REQUEST_SCHEMA` / `RESPONSE_SCHEMA` | Operation -> Schema | REST payloads |
| `SENDS` | Service -> Queue | async sender |
| `RECEIVES_FROM` | Service -> Queue | async consumer |
| `CARRIES` | Queue -> Message | message type on queue |
| `CONFORMS_TO` | Message -> Schema | message payload schema |
| `DEAD_LETTERS_TO` | Queue -> Queue | DLQ relationship |

Dependency semantics: `A -[:CALLS]-> Operation <-[:PROVIDES]- B` means A synchronously depends on
B; `A -[:SENDS]-> Queue <-[:RECEIVES_FROM]- B` means a message flow A -> Queue -> B. The derived
views `SYNC_DEPENDS_ON`/`ASYNC_FLOW_TO` (`app/analysis/dependencies.py`) are computed at query
time, never materialized/stored — this keeps the graph free of redundant truths that could drift
out of sync with their source relations.

Every relation carries an `evidence_ids: list[str]` property naming the `Evidence.id`(s) that
declared or observed it. There is no direct graph edge from a relation to `Evidence` — look the ids
up via `MATCH (e:Evidence) WHERE e.id IN r.evidence_ids`, or use `GET /api/services/{id}/evidence` /
`GET /api/queues/{id}/evidence` / `GET /api/evidence/{id}`. See [`evidence.md`](evidence.md) for the
full `Evidence` shape.

## Fact/Evidence invariants (11H)

These are the two invariants the whole runtime-correctness effort (11H) exists to guarantee, and
they're the single most important thing to understand about how this graph behaves under repeated,
partial, or conflicting imports:

1. **A fact exists in the graph if and only if at least one piece of supporting `Evidence` exists
   for it.** A relation is never persisted, and never survives, with an empty `evidence_ids` list.
2. **Removing `DECLARED` evidence never removes `OBSERVED` evidence, and vice versa.** The two are
   independent; a relation's evidence list can hold both kinds at once, or just one.

The concrete consequence: if a relation was both declared (e.g. in an OpenAPI spec) and observed
(via real OpenTelemetry traffic), and a later reimport removes the declaration (the route was
deleted from the spec, or the whole service stopped being scanned), the relation is **not**
deleted — it degrades from `CONFIRMED` to `OBSERVED_ONLY`, because its `OBSERVED` evidence is still
there:

```
DECLARED + OBSERVED
       |
 remove stale declaration
       v
   OBSERVED_ONLY
```

Before 11H-A (`12a7a0d`), the reconciliation query that strips a service's stale declared facts on
reimport did not distinguish evidence types, and could delete a relation's *entire* evidence list —
including its `OBSERVED` evidence — the moment its declaration went stale. `_EXPIRE_RELATIONS_QUERY`
(`app/graph/importer.py`) now only ever removes the specific `DECLARED` evidence ids that belong to
the reimporting service, and only deletes the relation itself once its evidence list is truly empty.
A relation declared by multiple services (e.g. a shared `CARRIES` edge on a queue two services both
publish/consume) keeps accumulating each contributor's evidence independently, and only loses one
contributor's evidence when that specific service stops declaring the relation — never another
service's.

### Status vocabulary

A relation's status (`CONFIRMED` / `OBSERVED_ONLY` / `NOT_OBSERVED_IN_WINDOW`) is **derived at query
time** from which evidence types back it in a given environment/time window — it is never itself a
stored property:

| Status | Meaning |
|---|---|
| `CONFIRMED` | Declared **and** observed in this environment/window |
| `OBSERVED_ONLY` | Observed, with no declared evidence at all (or none matching) |
| `NOT_OBSERVED_IN_WINDOW` | Declared, but not observed in this specific environment/window — never "obsolete", "unused", or "dead"; absence of observation is not evidence of absence. See [`opentelemetry.md`](opentelemetry.md) for how a coverage classification qualifies how much weight this status should carry. |

## Observed `PROVIDES` for runtime-discovered operations (11H-D)

A REST route can be discovered purely at runtime — a `CLIENT`/`SERVER` span pair for a route no
OpenAPI document has ever declared. When that happens, the resolver mints an `Operation` node for it
(`discovery_status = OBSERVED_ONLY`) and, since 11H-D (`0559509`), also emits an **observed
`PROVIDES`** relation for it:

```
Service -[:PROVIDES {OBSERVED evidence}]-> ObservedOnlyOperation
```

alongside the `CALLS` relation from the caller. This is deliberately never done for an
already-`DECLARED` operation — it already has a real `PROVIDES` edge from the OpenAPI import, so a
redundant observed one would be pure noise. The point of doing it for the observed-only case is that
the provider side of a runtime-discovered operation becomes itself confirmable/visible to
blast-radius and telemetry-coverage analyses, not just the caller side.

If that same route is later genuinely declared (a real OpenAPI document adds it), the declared
import must reconcile onto the **same** `Operation` node, not mint a duplicate — this depends
entirely on the id-normalization rule in [`canonical-model.md`](canonical-model.md) (operation ids
always built from the full service id). Get this wrong and a later declaration silently creates a
second, disconnected node instead of merging; 11H-D's own integration test suite
(`tests/integration/test_telemetry_api.py`) has a dedicated test for exactly this reconciliation
path, asserting one node with both `DECLARED` and `OBSERVED` evidence types on its `PROVIDES` edge.
