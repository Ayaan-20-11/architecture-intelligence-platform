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


# O1-O5 (spec §51/§52) answer "what happened at runtime", scoped by a configured default
# environment/window rather than any entity mentioned in the question (see
# app/analysis/registry.py::execute()'s since/environment kwargs) - none of these five need an
# entity_label. Ordered most-specific-keyword-combination first (O3/O4/O5, each pairs two distinct
# concepts) before the single-concept O2/O1 patterns, since "observed"/"beobachtet" appears in all
# five and a looser pattern earlier in the list would shadow a more specific one later.
_O3_OBSERVED_ONLY_RE = _compile(
    r"(?:undocumented|undokumentiert\w*).*(?:observ\w*|beobacht\w*)|"
    r"(?:observ\w*|beobacht\w*).*(?:undocumented|undokumentiert\w*)"
)
_O4_DECLARED_ONLY_RE = _compile(
    r"(?:declared|deklariert\w*).*(?:not\s+observed|nicht\s+beobachtet)|"
    r"(?:not\s+observed|nicht\s+beobachtet).*(?:declared|deklariert\w*)"
)
_O5_TELEMETRY_COVERAGE_RE = _compile(
    r"no\s+telemetry|keine\s+telemetrie|telemetry\s+coverage|telemetrie[- ]?abdeckung"
)
_O2_CONFIRMED_RE = _compile(
    r"confirmed\b|best(?:ä|ae)tigt\w*|"
    r"(?:declared\s+and\s+observed|documented\s+and\s+observed|dokumentiert\w*.*beobacht\w*)"
)
_O1_OBSERVED_RE = _compile(
    r"(?:architecture\s+)?relationships?.*(?:actually\s+)?observ\w*|"
    r"observ\w*.*(?:architecture\s+)?relationships?|"
    r"architekturbeziehungen.*beobacht\w*|was\s+wurde\s+(?:tats(?:ä|ae)chlich\s+)?beobachtet"
)

PATTERNS: list[IntentPattern] = [
    IntentPattern(ArchitectureIntent.QUEUES_WITHOUT_SENDERS, _NO_SENDER_RE, None),
    IntentPattern(ArchitectureIntent.QUEUES_WITHOUT_CONSUMERS, _NO_CONSUMER_RE, None),
    IntentPattern(ArchitectureIntent.QUEUE_SENDERS, _QUEUE_SENDERS_RE, "Queue"),
    IntentPattern(ArchitectureIntent.QUEUE_CONSUMERS, _QUEUE_CONSUMERS_RE, "Queue"),
    IntentPattern(ArchitectureIntent.BLAST_RADIUS, _BLAST_RADIUS_RE, "Service"),
    IntentPattern(ArchitectureIntent.OBSERVED_ONLY_RELATIONS, _O3_OBSERVED_ONLY_RE, None),
    IntentPattern(ArchitectureIntent.DECLARED_ONLY_RELATIONS, _O4_DECLARED_ONLY_RE, None),
    IntentPattern(ArchitectureIntent.TELEMETRY_COVERAGE, _O5_TELEMETRY_COVERAGE_RE, None),
    IntentPattern(ArchitectureIntent.CONFIRMED_RELATIONS, _O2_CONFIRMED_RE, None),
    IntentPattern(ArchitectureIntent.OBSERVED_RELATIONS, _O1_OBSERVED_RE, None),
]
