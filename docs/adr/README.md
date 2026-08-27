# Architecture Decision Records

Numbered, immutable records of significant architectural decisions and the reasoning behind them —
see [`architecture.md`](../architecture.md#architecture-principles) for how these map onto the
project's stated architecture principles.

| ADR | Decision |
|---|---|
| [0001](0001-use-neo4j.md) | Use Neo4j as the graph store |
| [0002](0002-canonical-model.md) | A shared Canonical Model decouples adapters from the graph |
| [0003](0003-evidence-as-first-class-concept.md) | Evidence is a first-class, persisted concept |
| [0004](0004-deterministic-before-generative.md) | Deterministic analyses before generative ones |
| [0005](0005-llm-is-not-source-of-truth.md) | The LLM is not a source of truth, and access is read-only by design |
| [0006](0006-declared-vs-observed.md) | Declared and observed architecture are independent evidence sources |
| [0007](0007-do-not-store-full-traces-in-neo4j.md) | Never store full traces or raw span payloads in Neo4j |
| [0008](0008-apache-2.0-license.md) | License under Apache License 2.0 |

A new ADR is numbered sequentially and never renumbered or deleted — if a decision is superseded,
add a new ADR and mark the old one's Status as `Superseded by NNNN`.
