# Adapter Development

AIP has two kinds of extension point — one for a new *declared* architecture source, one for a new
*runtime observation* source. The conceptual interfaces:

```python
class ArchitectureSourceAdapter(Protocol):
    def supports(self, source: Source) -> bool: ...
    def load(self, source: Source) -> ArchitectureModel: ...


class ObservationSourceAdapter(Protocol):
    def ingest(self, source: Any) -> ObservationBatch: ...
```

**Note on current implementation status:** today's three declared adapters
(`app/ingestion/openapi_adapter.py`, `asyncapi_adapter.py`, `manifest_adapter.py`) and the runtime
adapter (`app/telemetry/adapter.py`) are plain functions, not classes implementing these `Protocol`s
— e.g. `parse_openapi(document, *, service_id, source_file, source_revision=None) ->
ArchitectureModel`. The `Protocol` shapes above describe the *target* extension point a future,
pluggable adapter registry would formalize; they are not a claim that the current code already
implements them as classes. What every existing adapter already honors, and what a new one must
honor too, is the *contract* those Protocols describe:

## What a declared-source adapter must produce

An `ArchitectureModel` (`app/canonical/model.py`) — never a partial or adapter-specific shape. In
practice that means:

- Every entity id must be built with `app/canonical/ids.py`'s deterministic formatters, never an
  ad-hoc string and never anything derived from a local filesystem path (see
  [`canonical-model.md`](canonical-model.md) for why, including the specific bug class this
  prevents).
- Every `Relation` must carry `evidence_ids` pointing at a real `Provenance`/`Evidence` record the
  same adapter call also returns in `ArchitectureModel.provenance` — an adapter must never produce
  a fact with no supporting evidence (see [`graph-model.md`](graph-model.md)'s fact/evidence
  invariant).
- An adapter should only extract information it can reliably derive from its own source format — see
  how `manifest_adapter.py` deliberately extracts *only* REST-caller information OpenAPI can't
  express, rather than duplicating anything OpenAPI/AsyncAPI already cover
  ([`ingestion.md`](ingestion.md)).

## What a runtime-source adapter must produce

An `ObservationBatch` (`app/telemetry/model.py`): possibly-new entities (`ObservedOnlyEntity` stubs
for anything not already declared), evidence-backed `ObservedFactCandidate`s, and
`UnresolvedObservation`s for anything that couldn't be resolved with confidence. The existing
OpenTelemetry adapter's own rules are the model to follow for a new runtime source:

- Never guess an identity from an unreliable signal — report an `UnresolvedObservation` with a
  reason code instead (see [`opentelemetry.md`](opentelemetry.md)'s no-guessing rule and fixed
  reason-code set).
- Only read from an explicit, documented attribute/field allowlist — never persist a raw payload
  (see [`security-model.md`](security-model.md)).
- Emit deterministic evidence ids (`app/canonical/ids.py::observed_evidence_id`) so repeated
  observations of the same fact merge into one evidence bucket instead of accumulating duplicates.

## Wiring a new adapter in

There's no plugin registry yet — a new adapter is wired in the same way the existing three are: a
new module under `app/ingestion/` (or `app/telemetry/` for a runtime source), invoked from
`app/ingestion/pipeline.py` (or the OTLP request handler in `app/api/telemetry.py`) alongside its
siblings.
## Worked example: a tiny declared-source adapter

The following is a deliberately small, non-production example. It shows the complete shape of a
declared-source adapter without adding another real source format to AIP.

Imagine a toy format called `toy-arch.json`:

```json
{
  "service": "checkout",
  "operations": [
    {"method": "GET", "path": "/orders"}
  ]
}
```

A toy adapter could read that file, construct canonical IDs, attach provenance, and return an
`ArchitectureModel`:

```python
import json
from pathlib import Path

from app.canonical import ids
from app.canonical.model import ArchitectureModel, Operation, Relation, Service
from app.provenance.model import Provenance


def load_toy_document(path: Path) -> dict:
    return json.loads(path.read_text())


def parse_toy(
    document: dict,
    *,
    source_file: str,
    source_revision: str | None = None,
) -> ArchitectureModel:
    service_slug = document["service"]

    service = Service(
        id=ids.service_id(service_slug),
        name=service_slug,
    )

    operations = [
        Operation(
            id=ids.operation_id(
                service.id,
                entry["method"],
                entry["path"],
            ),
            service_id=service.id,
            method=entry["method"].upper(),
            path=entry["path"],
        )
        for entry in document.get("operations", [])
    ]

    evidence = Provenance(
        id=ids.evidence_id(
            "TOY",
            service_slug,
            source_revision,
        ),
        source_type="TOY",
        source_file=source_file,
        source_revision=source_revision,
    )

    relations = [
        Relation(
            type="PROVIDES",
            source_id=service.id,
            target_id=operation.id,
            evidence_ids=[evidence.id],
        )
        for operation in operations
    ]

    return ArchitectureModel(
        services=[service],
        operations=operations,
        relations=relations,
        provenance=[evidence],
    )
```

### Why this satisfies the adapter contract

The example follows the same contract as the existing adapters:

- `Service` uses `ids.service_id()`.
- Each `Operation` uses `ids.operation_id()`.
- The adapter returns an `ArchitectureModel`.
- Source provenance is returned with the model.
- No local filesystem path is used to construct entity IDs.
- The example does not introduce a new production source format.

### Wiring the adapter into the pipeline

A real adapter would be imported and invoked from `app/ingestion/pipeline.py` alongside the
existing OpenAPI, AsyncAPI, and manifest adapters.

Conceptually, the pipeline would:

1. Detect the toy source.
2. Load it with `load_toy_document()`.
3. Parse it with `parse_toy()`.
4. Add the returned `ArchitectureModel` to the models being merged.

For example:

```python
from app.ingestion.toy_adapter import load_toy_document, parse_toy

document = load_toy_document(source.path)

model = parse_toy(
    document,
    source_file=str(source.path),
    source_revision=source.revision,
)

partials_by_service[source.service_id].append(model)
```

This example is illustrative only. It does not require creating `toy_adapter.py` or wiring the toy
format into the production scanner.
