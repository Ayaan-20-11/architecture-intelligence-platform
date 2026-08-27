# 6. Declared and observed architecture are independent evidence sources

Status: Accepted

## Context

OpenAPI/AsyncAPI/the Architecture Manifest describe what a system's architecture is *declared* to
be. OpenTelemetry traces (H4/11H) describe what actually *happened* at runtime. These can and do
diverge — an undocumented call that was never declared, a declared dependency that's gone quiet, or
(the common case) a dependency that's both declared and actively observed. Collapsing these into one
"is this relation real" boolean would lose exactly the information — drift between documentation and
reality — that makes comparing them valuable in the first place.

## Decision

Keep `DECLARED` and `OBSERVED` as independent `Evidence.evidence_type` values on the same
relationship, and derive a comparison status from their combination rather than storing the status
itself:

- `CONFIRMED` — declared and observed
- `OBSERVED_ONLY` — observed, never declared anywhere (an undocumented real dependency)
- `NOT_OBSERVED_IN_WINDOW` — declared, not seen in the current window — never described as
  "obsolete"/"unused"/"dead", because absence of observation isn't proof of absence (11H's coverage
  qualification — `SUFFICIENT`/`PARTIAL`/`NONE`/`UNKNOWN` — exists specifically to make that
  distinction explicit rather than implied)

Removing a stale declaration on reimport degrades `CONFIRMED` to `OBSERVED_ONLY` — it never deletes
a relation that still has observed evidence (the 11H evidence-reconciliation invariant; see
[0003](0003-evidence-as-first-class-concept.md)).

Queue and Message are, separately, always distinct entities from Schema — transport/DLQ semantics
must stay independent of payload semantics so they can be analyzed and versioned independently.

## Consequences

- `app/analysis/runtime.py`'s O1-O5 queries compute status from evidence-type combinations at query
  time; no status field is ever written and later allowed to drift out of sync with the evidence
  that justifies it.
- A relation's declared and observed identity must resolve to the *same* graph entity for this to
  work — `app/telemetry/service_resolver.py`'s exact-name matching exists for exactly this reason,
  and getting the timing wrong (observing traffic before the corresponding declaration is imported)
  is a real failure mode the runtime demo had to be hardened against (see
  `examples/runtime-demo/traffic_generator.py`'s `wait_for_declared_import`).
- `OBSERVED PROVIDES` (11H-D) extends this principle to operations discovered only at runtime, with
  no declared provider yet — the same declared/observed independence, one level down from
  relationships to the operations they connect.
