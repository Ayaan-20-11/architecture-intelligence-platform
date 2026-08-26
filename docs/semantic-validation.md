# Natural-Language Query & Semantic Validation

`POST /api/query` accepts a natural-language question and answers it one of two ways:

```
Question -> intent classification
   -> known intent:      call the matching deterministic analysis directly (see analyses.md)
   -> unrecognized:       Cypher generation -> Cypher validation -> read-only Neo4j execution
                              -> rows + provenance -> answer composition
```

A known-intent question never touches the LLM's Cypher-generation path at all — it's answered by
the exact same deterministic function its equivalent REST endpoint calls
(`app/analysis/registry.py`). Only a genuinely unrecognized question falls through to the
LLM-generated-Cypher path (`app/ai/question_service.py`'s `ArchitectureQuestionService`).

## The generated-Cypher path

```
question + fixed graph schema -> CypherGenerator -> CypherValidator
   -> ReadOnlyGraphExecutor -> rows + provenance -> AnswerComposer
```

- **`CypherGenerator`** (`app/ai/cypher_generator.py`) turns the question into a candidate Cypher
  string, given the fixed graph schema — it never sees live data, only the schema shape.
- **`CypherValidator`** (`app/ai/cypher_validator.py::validate_cypher`) is the hard gate. It:
  - strips string/comment content before scanning (so a forbidden keyword can't hide inside a
    quoted string literal),
  - rejects multiple statements (`;`),
  - allowlists only `MATCH`, `OPTIONAL MATCH`, `WHERE`, `WITH`, `RETURN`, `ORDER BY`, `LIMIT` by
    rejecting a fixed forbidden-keyword set that covers everything else a real Cypher grammar would
    otherwise need to allowlist explicitly: `CREATE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `MERGE`,
    `DROP`, `LOAD`, `CALL`, `UNWIND`, `FOREACH`, `UNION`, `START`, `USE`, `SHOW`, `EXPLAIN`,
    `PROFILE`, `GRANT`, `DENY`, `REVOKE`, `TERMINATE`, `INDEX`, `CONSTRAINT`, `ALTER`, `RENAME`,
    `DBMS`,
  - requires a `RETURN` clause,
  - rejects any node label or relationship type not in the graph's known set (`app/graph/importer.
    py::NODE_LABELS` / `app/graph/reconciliation.py::KNOWN_RELATION_TYPES`),
  - rejects unbounded variable-length traversals and clamps any bounded one to a configured
    `max_depth` (default 5),
  - clamps or appends a `LIMIT` to a configured `max_result_rows` (default 100).
- **`ReadOnlyGraphExecutor`** runs the validated query against a read-only Neo4j session — the LLM
  layer never receives Neo4j credentials directly, and never gets a code path that could mutate the
  graph even if the validator had a gap.
- **`AnswerComposer`** (`app/ai/answer_composer.py`) builds the final natural-language answer
  strictly from the result rows and their provenance — it never invents a fact the rows don't
  support.

The generated Cypher is always returned alongside the answer (`QueryResponse.cypher` in
`app/api/query.py`), so every LLM-mediated answer is independently traceable and reproducible.

See [`security-model.md`](security-model.md) for why this whole path treats LLM output as untrusted
input, and [`configuration.md`](configuration.md) for how `max_depth`/`max_result_rows` and the
deterministic-routing threshold are configured.
