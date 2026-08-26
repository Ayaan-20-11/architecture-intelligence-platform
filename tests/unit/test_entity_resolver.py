from app.intent.entity_resolver import resolve

QUEUES = [
    ("queue:payment-q", "payment-q"),
    ("queue:invoice-q", "invoice-q"),
    ("queue:payment-dlq", "payment-dlq"),
]
SERVICES = [
    ("service:order-service", "OrderService"),
    ("service:payment-service", "PaymentService"),
]


def test_exact_match_resolves():
    result = resolve(QUEUES, "payment-q")
    assert result.id == "queue:payment-q"


def test_normalization_treats_spaces_hyphens_and_nothing_as_equivalent():
    for variant in ["payment-q", "payment q", "paymentq", "Payment-Q", "  payment-q  "]:
        assert resolve(QUEUES, variant).id == "queue:payment-q"


def test_normalization_treats_pascal_case_and_hyphenated_slug_as_equivalent():
    # "OrderService" (display name) vs. "order-service" (a plausible NL phrasing of the slug)
    # must normalize identically - a naive whitespace-to-hyphen rule would fail this.
    for variant in ["OrderService", "order-service", "order service", "orderservice"]:
        assert resolve(SERVICES, variant).id == "service:order-service"


def test_ambiguous_exact_or_partial_match_returns_none():
    # "payment" is a substring of both payment-q and payment-dlq - must not guess.
    assert resolve(QUEUES, "payment") is None


def test_no_match_returns_none():
    assert resolve(QUEUES, "does-not-exist") is None


def test_unique_partial_match_resolves():
    assert resolve(QUEUES, "invoice").id == "queue:invoice-q"
