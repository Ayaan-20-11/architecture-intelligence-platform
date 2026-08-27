# 1. Use Neo4j as the graph store

Status: Accepted

## Context

The core hypothesis of this project is that an Architecture Knowledge Graph — services, REST
operations, queues, messages, schemas, and their typed relationships — can be built automatically
from OpenAPI/AsyncAPI specs and queried for real architectural questions: who calls this operation,
which queues have a sender but no consumer, what's the mixed sync/async blast radius of a service
going down. Those are graph-traversal questions (variable-depth, typed-edge) by nature.

A relational store would need either a fixed number of self-joins per query (breaking down for
variable-depth traversals like blast radius) or a recursive-CTE approach that's far more awkward to
express and reason about than a graph traversal. A document store has no native concept of a typed,
directed relationship at all — it would need to reimplement graph semantics in application code.

## Decision

Use Neo4j as the sole persistent graph store, queried via Cypher.

## Consequences

- Node labels (`Service`, `Operation`, `Queue`, `Message`, `Schema`, `Evidence`) and relationship
  types (`PROVIDES`, `CALLS`, `SENDS`, `RECEIVES_FROM`, `CARRIES`, `CONFORMS_TO`,
  `DEAD_LETTERS_TO`, `REQUEST_SCHEMA`, `RESPONSE_SCHEMA`) map directly onto Cypher's property-graph
  model — see [`graph-model.md`](../graph-model.md).
- The five deterministic analyses (`app/analysis/`) and the mixed-architecture blast radius (A5,
  configurable max traversal depth) are fixed, parameterized Cypher queries — no application-level
  graph-traversal code to maintain.
- Neo4j is the only external persistent infrastructure dependency this project has — see
  [0002](0002-canonical-model.md) for how the Canonical Model keeps that dependency isolated to one
  layer (`app/graph/`) rather than leaking into every adapter.
