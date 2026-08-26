import re
from dataclasses import dataclass
from typing import Literal

from app.intent.model import ArchitectureIntent


@dataclass(frozen=True)
class IntentPattern:
    intent: ArchitectureIntent
    regex: re.Pattern[str]
    entity_label: Literal["Service", "Queue"] | None


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# A3/A4 are keyword-combination matches (not one fixed sentence): the spec itself uses two
# different phrasings for A4 alone ("queues with a consumer but no sender" vs. the live-test
# regression text "what queues have a consumer but no known sender?"), so matching on "queue" +
# a no-sender/no-consumer phrase (order-independent, via .search rather than an anchored
# full-sentence match) is more robust than enumerating literal sentences.
_NO_SENDER_RE = _compile(
    r"queues?.*(?:no\s+known\s+senders?|no\s+senders?|without\s+(?:a\s+|any\s+)?"
    r"(?:known\s+)?senders?|keinen\s+sender|ohne\s+sender)"
)
_NO_CONSUMER_RE = _compile(
    r"queues?.*(?:no\s+consumers?|without\s+(?:a\s+|any\s+)?consumers?|keinen\s+consumer|ohne\s+consumer)"
)

# A1/A2/A5 are anchored full-sentence templates with a captured entity mention. The anchor words
# ("to"/"from"/"von"/"vom") are mandatory, never optional - this, together with strictly
# label-scoped entity resolution, is what keeps unrelated free-text questions from accidentally
# matching (see tests/unit/test_intent_patterns_and_router.py's invariant-pinning cases).
_QUEUE_SENDERS_RE = _compile(
    r"^(?:who\s+sends?\s+to|which\s+services?\s+sends?\s+to|wer\s+sendet\s+an|"
    r"welche\s+services?\s+senden\s+an)\s+(?:the\s+|die\s+|der\s+)?(?P<entity>.+?)"
    r"(?:\s+queue)?\??$"
)
_QUEUE_CONSUMERS_RE = _compile(
    r"^(?:who\s+(?:consumes?|receives?)\s+from|which\s+services?\s+(?:consumes?|receives?)\s+from|"
    r"wer\s+konsumiert\s+von|welche\s+services?\s+empfangen\s+von)\s+"
    r"(?:the\s+|die\s+|der\s+)?(?P<entity>.+?)(?:\s+queue)?\??$"
)
_BLAST_RADIUS_RE = _compile(
    r"^(?:what\s+depends\s+on|which\s+services?\s+depends?\s+on|blast\s+radius\s+of|"
    r"welche\s+services?\s+h(?:ä|ae)ngen\s+(?:von|vom))\s+(?:the\s+|dem\s+)?"
    r"(?P<entity>.+?)(?:\s+ab)?\??$"
)

PATTERNS: list[IntentPattern] = [
    IntentPattern(ArchitectureIntent.QUEUES_WITHOUT_SENDERS, _NO_SENDER_RE, None),
    IntentPattern(ArchitectureIntent.QUEUES_WITHOUT_CONSUMERS, _NO_CONSUMER_RE, None),
    IntentPattern(ArchitectureIntent.QUEUE_SENDERS, _QUEUE_SENDERS_RE, "Queue"),
    IntentPattern(ArchitectureIntent.QUEUE_CONSUMERS, _QUEUE_CONSUMERS_RE, "Queue"),
    IntentPattern(ArchitectureIntent.BLAST_RADIUS, _BLAST_RADIUS_RE, "Service"),
]
