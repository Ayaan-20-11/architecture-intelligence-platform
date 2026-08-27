# 5. The LLM is not a source of truth, and access is read-only by design

Status: Accepted

## Context

The natural-language query layer (`Question -> Cypher generation -> Cypher validator -> read-only
Neo4j execution -> rows + provenance -> LLM explanation`) puts an LLM between the user and a graph
that's meant to be a trustworthy record of architecture. Two distinct risks follow from that
position: the LLM could be tricked or could hallucinate its way into mutating the graph (via
generated Cypher), and the LLM could state something in its explanation that isn't actually
supported by the query's result rows.

## Decision

Treat LLM output as untrusted input, permanently, not as a temporary PoC shortcut:

- `CypherValidator` (`app/ai/cypher_validator.py`) enforces an allowlist —only `MATCH`,
  `OPTIONAL MATCH`, `WHERE`, `WITH`, `RETURN`, `ORDER BY`, `LIMIT` are permitted. `CREATE`,
  `DELETE`, `DETACH DELETE`, `SET`, `REMOVE`, `MERGE`, `DROP`, `LOAD CSV`, `CALL` are rejected
  before anything reaches Neo4j.
- `ReadOnlyGraphExecutor` runs against a read-only Neo4j user — a second, defense-in-depth layer
  below the validator, not a substitute for it.
- The LLM never receives direct Neo4j credentials.
- `AnswerComposer` builds the answer strictly from the query's result rows and their evidence/
  provenance — never inventing a fact the graph didn't actually return.
- The generated Cypher is shown to the user for traceability, not hidden behind the explanation.

## Consequences

- A prompt-injection attempt embedded in a natural-language question, or in data the LLM has been
  exposed to, cannot escalate into a graph mutation — the validator and the read-only DB user are
  both structural guarantees, not prompt-level ones.
- The LLM query subsystem is built behind a provider-abstraction interface
  (`app/ai/provider.py`) specifically so this project isn't locked to one LLM vendor — swapping
  providers doesn't change the trust boundary above.
- Because the LLM is additive rather than load-bearing (see
  [0004](0004-deterministic-before-generative.md)), disabling it entirely (no API key configured)
  degrades the platform to "no natural-language query", not "no architecture intelligence" — the
  five deterministic analyses and the graph API are unaffected.
