from pathlib import Path

import pytest

from app.canonical import ids
from app.canonical.model import ArchitectureModel, Service
from app.ingestion.manifest_adapter import ManifestResolutionError
from app.ingestion.pipeline import import_sources, merge_models
from app.validation.canonical_validation import CanonicalValidationError

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"


def test_import_sources_real_examples_end_to_end():
    model = import_sources(EXAMPLES_DIR)

    service_ids = {s.id for s in model.services}
    assert service_ids == {
        ids.service_id("order-service"),
        ids.service_id("product-service"),
        ids.service_id("payment-service"),
        ids.service_id("invoice-service"),
    }

    calls = [r for r in model.relations if r.type == "CALLS"]
    assert len(calls) == 1
    assert calls[0].source_id == ids.service_id("order-service")
    assert calls[0].target_id == ids.operation_id("product-service", "GET", "/products/{id}")

    queue_names = {q.name for q in model.queues}
    assert queue_names == {
        "payment-q",
        "invoice-q",
        "unused-q",
        "unknown-producer-q",
        "payment-dlq",
    }

    dead_letters = [r for r in model.relations if r.type == "DEAD_LETTERS_TO"]
    assert len(dead_letters) == 1
    assert dead_letters[0].source_id == ids.queue_id("payment-q")
    assert dead_letters[0].target_id == ids.queue_id("payment-dlq")


def test_import_sources_is_idempotent_across_repeated_calls():
    first = import_sources(EXAMPLES_DIR)
    second = import_sources(EXAMPLES_DIR)
    assert {s.id for s in first.services} == {s.id for s in second.services}
    assert len(first.relations) == len(second.relations)


def test_import_sources_raises_on_unresolvable_manifest_call(tmp_path):
    service_dir = tmp_path / "order-service"
    service_dir.mkdir()
    (service_dir / "openapi.yaml").write_text(
        "openapi: '3.1.0'\ninfo:\n  title: OrderService\npaths: {}\n"
    )
    (service_dir / "architecture.yaml").write_text(
        "service: order-service\ncalls:\n  - service: product-service\n    operationId: nonExistent\n"
    )
    with pytest.raises(ManifestResolutionError):
        import_sources(tmp_path)


def test_import_sources_raises_on_canonical_violation(tmp_path):
    service_dir = tmp_path / "order-service"
    service_dir.mkdir()
    (service_dir / "asyncapi.yaml").write_text(
        "asyncapi: '2.6.0'\n"
        "info:\n  title: OrderService\n"
        "channels:\n"
        "  payment-q:\n"
        "    x-dead-letter-queue: payment-q\n"
        "    publish:\n"
        "      message:\n"
        "        name: PaymentRequested\n"
    )
    with pytest.raises(CanonicalValidationError):
        import_sources(tmp_path)


def test_merge_models_dedupes_entities_across_partial_models_first_wins():
    first = ArchitectureModel(services=[Service(id="service:x", name="X-from-openapi")])
    second = ArchitectureModel(services=[Service(id="service:x", name="X-from-asyncapi")])
    merged = merge_models([first, second])
    assert len(merged.services) == 1
    assert merged.services[0].name == "X-from-openapi"
