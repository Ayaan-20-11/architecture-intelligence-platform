from collections import defaultdict
from pathlib import Path

from app.ingestion.scanner import SpecificationType, scan_directory

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"


def test_scan_directory_finds_expected_sources(tmp_path):
    (tmp_path / "order-service").mkdir()
    (tmp_path / "order-service" / "openapi.yaml").write_text("openapi: {}")
    (tmp_path / "order-service" / "asyncapi.yaml").write_text("asyncapi: {}")
    (tmp_path / "order-service" / "architecture.yaml").write_text("service: order-service")
    (tmp_path / "product-service").mkdir()
    (tmp_path / "product-service" / "openapi.yaml").write_text("openapi: {}")

    sources = scan_directory(tmp_path)
    by_service = defaultdict(set)
    for source in sources:
        by_service[source.service_id].add(source.type)

    assert by_service["order-service"] == {
        SpecificationType.OPENAPI,
        SpecificationType.ASYNCAPI,
        SpecificationType.MANIFEST,
    }
    assert by_service["product-service"] == {SpecificationType.OPENAPI}


def test_scan_directory_ignores_non_directories(tmp_path):
    (tmp_path / "README.md").write_text("not a service dir")
    assert scan_directory(tmp_path) == []


def test_scan_directory_ignores_unrelated_files(tmp_path):
    (tmp_path / "order-service").mkdir()
    (tmp_path / "order-service" / "notes.txt").write_text("irrelevant")
    assert scan_directory(tmp_path) == []


def test_scan_real_examples_directory():
    sources = scan_directory(EXAMPLES_DIR)
    service_ids = {s.service_id for s in sources}
    assert service_ids == {"order-service", "product-service", "payment-service", "invoice-service"}

    by_service = defaultdict(set)
    for source in sources:
        by_service[source.service_id].add(source.type)
    assert by_service["order-service"] == {
        SpecificationType.OPENAPI,
        SpecificationType.ASYNCAPI,
        SpecificationType.MANIFEST,
    }
    assert by_service["product-service"] == {SpecificationType.OPENAPI}
    assert by_service["payment-service"] == {SpecificationType.ASYNCAPI}
    assert by_service["invoice-service"] == {SpecificationType.ASYNCAPI}
