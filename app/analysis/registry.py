import dataclasses
from collections.abc import Callable
from datetime import datetime

import neo4j

from app.analysis.blast_radius import blast_radius
from app.analysis.queues import (
    consumers_of_queue,
    queues_without_consumers,
    queues_without_senders,
    senders_of_queue,
)
from app.analysis.runtime import (
    confirmed_relations,
    declared_only_relations,
    observed_only_relations,
    observed_relations,
    telemetry_coverage,
)
from app.intent.model import ArchitectureIntent

# BLAST_RADIUS deliberately omits a max_depth override, relying on blast_radius.DEFAULT_MAX_DEPTH -
# the same default GET /api/analysis/services/{id}/blast-radius uses, so AC-H3-4 (this registry's
# results match the deterministic REST endpoints exactly) holds precisely rather than coincidentally.
# O1-O5 handlers read environment/since from p - injected by execute()'s kwargs below, never
# resolved by classify()/entity_resolver.py (spec §51: O1-O5 need no named entity, only a
# configured default environment/window - see app/intent/patterns.py's module docstring comment).
INTENT_HANDLERS: dict[ArchitectureIntent, Callable[[neo4j.Session, dict], list]] = {
    ArchitectureIntent.QUEUE_SENDERS: lambda session, p: senders_of_queue(session, p["queue_id"]),
    ArchitectureIntent.QUEUE_CONSUMERS: lambda session, p: consumers_of_queue(
        session, p["queue_id"]
    ),
    ArchitectureIntent.QUEUES_WITHOUT_CONSUMERS: lambda session, p: queues_without_consumers(
        session
    ),
    ArchitectureIntent.QUEUES_WITHOUT_SENDERS: lambda session, p: queues_without_senders(session),
    ArchitectureIntent.BLAST_RADIUS: lambda session, p: blast_radius(session, p["service_id"]),
    ArchitectureIntent.OBSERVED_RELATIONS: lambda session, p: observed_relations(
        session, environment=p["environment"], since=p["since"]
    ),
    ArchitectureIntent.CONFIRMED_RELATIONS: lambda session, p: confirmed_relations(
        session, environment=p["environment"], since=p["since"]
    ),
    ArchitectureIntent.OBSERVED_ONLY_RELATIONS: lambda session, p: observed_only_relations(
        session, environment=p["environment"], since=p["since"]
    ),
    ArchitectureIntent.DECLARED_ONLY_RELATIONS: lambda session, p: declared_only_relations(
        session, environment=p["environment"], since=p["since"]
    ),
    ArchitectureIntent.TELEMETRY_COVERAGE: lambda session, p: telemetry_coverage(
        session, environment=p["environment"], since=p["since"]
    ),
}


def _to_native(value):
    """Neo4j returns temporal properties as neo4j.time.DateTime, not datetime.datetime - the O1-O5
    dataclasses hold whatever Cypher returned (fine for a plain dataclass), but QueryResponse.rows
    is JSON-serialized by Pydantic, which rejects the neo4j type outright. A1-A5's dataclasses never
    carried datetime fields, so this is a shallow, no-op-elsewhere conversion new only to O1-O5."""
    return value.to_native() if hasattr(value, "to_native") else value


def execute(
    session: neo4j.Session,
    intent: ArchitectureIntent,
    parameters: dict,
    *,
    since: datetime | None = None,
    environment: str | None = None,
) -> list[dict]:
    """Runs the existing tested analysis for a deterministically-routed intent - the router never
    generates Cypher itself (spec §6.7). since/environment are the O1-O5 handlers' window/scope
    (spec §51 Decision 2: always defaulted by the caller, never parsed from question text) - merged
    into parameters rather than added as new IntentResult.parameters keys, so classify() stays
    entirely unaware of them."""
    params = dict(parameters)
    if since is not None:
        params.setdefault("since", since)
    if environment is not None:
        params.setdefault("environment", environment)
    return [
        {key: _to_native(value) for key, value in dataclasses.asdict(row).items()}
        for row in INTENT_HANDLERS[intent](session, params)
    ]
