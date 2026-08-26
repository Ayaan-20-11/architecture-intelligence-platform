from app.intent.entity_resolver import resolve
from app.intent.model import ArchitectureIntent, IntentResult
from app.intent.patterns import PATTERNS

_UNKNOWN = IntentResult(intent=ArchitectureIntent.UNKNOWN, confidence=0.0, parameters={})


def classify(
    question: str,
    *,
    candidates: dict[str, list[tuple[str, str]]],
    threshold: float = 0.90,
) -> IntentResult:
    """Recognizes a standard EN/DE phrasing of one of the five deterministic analyses and
    resolves any entity mention (spec §6.6). Never guesses: an unresolvable/ambiguous entity
    mention, or a question matching no known template, is UNKNOWN (spec §6.9)."""
    text = question.strip()

    for pattern in PATTERNS:
        match = pattern.regex.search(text)
        if match is None:
            continue

        parameters: dict[str, str | int] = {}
        if pattern.entity_label is not None:
            raw_entity = match.group("entity").strip().rstrip("?.! \t")
            resolved = resolve(candidates[pattern.entity_label], raw_entity)
            if resolved is None:
                return _UNKNOWN
            param_key = "queue_id" if pattern.entity_label == "Queue" else "service_id"
            parameters[param_key] = resolved.id

        result = IntentResult(intent=pattern.intent, confidence=1.0, parameters=parameters)
        return result if result.confidence >= threshold else _UNKNOWN

    return _UNKNOWN
