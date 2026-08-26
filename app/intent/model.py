from enum import StrEnum

from pydantic import BaseModel, Field


class ArchitectureIntent(StrEnum):
    """The five deterministic analyses, plus UNKNOWN for anything else (spec §6.4)."""

    QUEUE_SENDERS = "A1_QUEUE_SENDERS"
    QUEUE_CONSUMERS = "A2_QUEUE_CONSUMERS"
    QUEUES_WITHOUT_CONSUMERS = "A3_QUEUES_WITHOUT_CONSUMERS"
    QUEUES_WITHOUT_SENDERS = "A4_QUEUES_WITHOUT_SENDERS"
    BLAST_RADIUS = "A5_BLAST_RADIUS"
    UNKNOWN = "UNKNOWN"


class IntentResult(BaseModel):
    intent: ArchitectureIntent
    confidence: float
    parameters: dict[str, str | int] = Field(default_factory=dict)
