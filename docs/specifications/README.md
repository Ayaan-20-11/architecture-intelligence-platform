# Specifications

The original design specifications this project was built from, in chronological order — kept as a
traceable design history alongside the current reference docs in [`docs/`](..). All translated to
English and consolidated here from their original PDF/root-level-Markdown form; content is otherwise
unchanged from the originals.

| Document | Covers |
|---|---|
| [`poc.md`](poc.md) | The original Proof of Concept: Canonical Model, OpenAPI/AsyncAPI/manifest adapters, Neo4j graph model, the five deterministic analyses (A1-A5), the read-only LLM query subsystem. |
| [`h1-h3-hardening.md`](h1-h3-hardening.md) | H1 (Evidence/Provenance persistence), H2 (Semantic Query Validator), H3 (Deterministic Intent Router). |
| [`h4-opentelemetry.md`](h4-opentelemetry.md) | H4: OpenTelemetry runtime observation, declared-vs-observed comparison. |
| [`11h-runtime-correctness-robustness.md`](11h-runtime-correctness-robustness.md) | 11H: evidence-reconciliation correctness, HTTP correlation robustness, partial instrumentation, observed `PROVIDES`, coverage qualification, the Collector-based demo. |
| [`h5-open-source-readiness.md`](h5-open-source-readiness.md) | H5: licensing, documentation, the runtime demo, CI/CD, community files, release process. |
| [`12g-public-repository-activation.md`](12g-public-repository-activation.md) | 12G: activating the project on real GitHub infrastructure — repository creation, CI verification, security features, releases. |

See [`docs/architecture.md`](../architecture.md#architecture-principles) and
[`docs/adr/`](../adr/) for how these design decisions map onto the system as it exists today, and
[`ROADMAP.md`](../../ROADMAP.md) for what's shipped versus planned.
