import pytest

from app.intent.model import ArchitectureIntent
from app.intent.router import classify

CANDIDATES = {
    "Queue": [
        ("queue:payment-q", "payment-q"),
        ("queue:invoice-q", "invoice-q"),
        ("queue:payment-dlq", "payment-dlq"),
    ],
    "Service": [
        ("service:order-service", "OrderService"),
        ("service:payment-service", "PaymentService"),
    ],
}


def classify_default(question: str):
    return classify(question, candidates=CANDIDATES)


# --- A1 queue senders ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "Who sends to payment-q?",
        "Who sends to the payment-q queue?",
        "Which services send to payment-q?",
        "Wer sendet an payment-q?",
        "Welche Services senden an payment-q?",
    ],
)
def test_a1_queue_senders_recognized(question):
    result = classify_default(question)
    assert result.intent == ArchitectureIntent.QUEUE_SENDERS
    assert result.parameters == {"queue_id": "queue:payment-q"}


# --- A2 queue consumers ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "Who consumes from payment-q?",
        "Who receives from payment-q?",
        "Which services receive from payment-q?",
        "Wer konsumiert von payment-q?",
        "Welche Services empfangen von payment-q?",
    ],
)
def test_a2_queue_consumers_recognized(question):
    result = classify_default(question)
    assert result.intent == ArchitectureIntent.QUEUE_CONSUMERS
    assert result.parameters == {"queue_id": "queue:payment-q"}


# --- A3 queues without consumers -------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "Which queues have no consumer?",
        "Queues without a consumer",
        "Welche Queues haben keinen Consumer?",
    ],
)
def test_a3_queues_without_consumers_recognized(question):
    result = classify_default(question)
    assert result.intent == ArchitectureIntent.QUEUES_WITHOUT_CONSUMERS
    assert result.parameters == {}


# --- A4 queues without senders -----------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "What queues have a consumer but no known sender?",
        "Queues with a consumer but no sender",
        "Queues without a sender",
        "Welche Queues haben keinen Sender?",
    ],
)
def test_a4_queues_without_senders_recognized(question):
    result = classify_default(question)
    assert result.intent == ArchitectureIntent.QUEUES_WITHOUT_SENDERS
    assert result.parameters == {}


# --- A5 blast radius -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "What depends on OrderService?",
        "Which services depend on OrderService?",
        "Blast radius of OrderService",
        "Welche Services hängen von OrderService ab?",
        "Welche Services hängen vom OrderService ab?",
    ],
)
def test_a5_blast_radius_recognized(question):
    result = classify_default(question)
    assert result.intent == ArchitectureIntent.BLAST_RADIUS
    assert result.parameters == {"service_id": "service:order-service"}


# --- ambiguity / unknown -----------------------------------------------------------------------


def test_ambiguous_entity_mention_is_unknown():
    # "payment" matches both payment-q and payment-dlq - must not guess (AC-H3-5).
    result = classify_default("Who sends to payment?")
    assert result.intent == ArchitectureIntent.UNKNOWN


def test_unrelated_question_is_unknown():
    result = classify_default("What is the meaning of life?")
    assert result.intent == ArchitectureIntent.UNKNOWN


def test_no_matching_entity_is_unknown():
    result = classify_default("Who sends to does-not-exist-q?")
    assert result.intent == ArchitectureIntent.UNKNOWN


def test_threshold_gate_forces_unknown_even_on_a_clean_match():
    result = classify("Which queues have no consumer?", candidates=CANDIDATES, threshold=1.1)
    assert result.intent == ArchitectureIntent.UNKNOWN


# --- invariant-pinning: exact collision risk checked against the existing /api/query tests -----


def test_who_sends_without_to_does_not_match_a1():
    # tests/integration/test_api.py uses "who sends payment-q?" (no "to") for LLM-path tests -
    # this must never be recognized as A1, or those tests' FakeProvider assertions would break.
    result = classify_default("who sends payment-q?")
    assert result.intent == ArchitectureIntent.UNKNOWN


def test_who_sends_to_services_matches_shape_but_resolves_unknown():
    # tests/integration/test_api.py uses "who sends to services?" for a 422 semantic-validator
    # test - the phrase matches A1's shape, but "services" isn't a real queue name, so it must
    # still fall back to UNKNOWN (and therefore the LLM path) rather than erroring or guessing.
    result = classify_default("who sends to services?")
    assert result.intent == ArchitectureIntent.UNKNOWN
