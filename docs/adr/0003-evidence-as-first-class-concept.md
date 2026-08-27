# 3. Evidence is a first-class, persisted concept

Status: Accepted

## Context

The original PoC tracked provenance (`source_type`, `source_file`, `source_revision`,
`evidence_type`) as an in-memory `Provenance` record attached during import, but never persisted it
as its own graph entity — a relationship existed or it didn't, with no queryable trail of *why*.
That made "traceable provenance" (an original acceptance criterion) true only in a weak sense: the
information existed transiently during import, not as something you could ask the graph about later.
It also couldn't support two facts that turned out to matter a lot once runtime observation (H4)
arrived: a relation can be asserted by more than one source (a shared `CARRIES` edge declared by two
services), and a relation can have *both* a declared and an observed basis at once.

## Decision

Persist `Evidence` as its own node label (`id`, `source_type`, `source_file`, `source_revision`,
`evidence_type`), added in Iteration 10A (H1). Every relationship carries an `evidence_ids: list[str]`
property naming the `Evidence.id`(s) that declared or observed it — not a direct graph edge to
`Evidence`, a property lookup (`MATCH (e:Evidence) WHERE e.id IN r.evidence_ids`).

## Consequences

- Provenance is queryable, not just producible: `GET /api/evidence`, `GET /api/evidence/{id}`,
  `GET /api/services/{id}/evidence`, `GET /api/queues/{id}/evidence`.
- A relation declared by multiple services accumulates each contributor's evidence independently,
  and only loses one contributor's evidence when that specific service stops declaring the
  relation — not when any one of them does.
- This is what made `evidence_type: DECLARED | OBSERVED` possible as an orthogonal axis once H4
  added runtime observation: the same relationship can carry both, and the *fact exists iff
  supporting evidence exists* / *removing DECLARED evidence ⇏ removing OBSERVED evidence*
  invariants (11H) are direct consequences of evidence being first-class rather than an in-memory
  side effect of import. See [`evidence.md`](../evidence.md) and
  [0006](0006-declared-vs-observed.md).
