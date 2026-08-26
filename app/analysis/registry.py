import dataclasses
from collections.abc import Callable

import neo4j

from app.analysis.blast_radius import blast_radius
from app.analysis.queues import (
    consumers_of_queue,
    queues_without_consumers,
    queues_without_senders,
    senders_of_queue,
)
from app.intent.model import ArchitectureIntent

# BLAST_RADIUS deliberately omits a max_depth override, relying on blast_radius.DEFAULT_MAX_DEPTH -
# the same default GET /api/analysis/services/{id}/blast-radius uses, so AC-H3-4 (this registry's
# results match the deterministic REST endpoints exactly) holds precisely rather than coincidentally.
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
}


def execute(session: neo4j.Session, intent: ArchitectureIntent, parameters: dict) -> list[dict]:
    """Runs the existing tested analysis for a deterministically-routed intent - the router never
    generates Cypher itself (spec §6.7)."""
    return [dataclasses.asdict(row) for row in INTENT_HANDLERS[intent](session, parameters)]
