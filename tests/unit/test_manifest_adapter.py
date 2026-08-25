from pathlib import Path

import pytest

from app.canonical import ids
from app.ingestion.manifest_adapter import (
    ManifestResolutionError,
    load_manifest_document,
    parse_manifest,
)
from app.ingestion.openapi_adapter import load_openapi_document, parse_openapi

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"


def test_resolves_calls_relation_via_operation_index():
    index = {("product-service", "getProduct"): "operation:product-service:GET:/products/{id}"}
    document = {
        "service": "order-service",
        "calls": [{"service": "product-service", "operationId": "getProduct"}],
    }
    model = parse_manifest(document, source_file="architecture.yaml", operation_index=index)
    [relation] = model.relations
    assert relation.type == "CALLS"
    assert relation.source_id == ids.service_id("order-service")
    assert relation.target_id == "operation:product-service:GET:/products/{id}"


def test_raises_on_unknown_operation_id():
    document = {
        "service": "order-service",
        "calls": [{"service": "product-service", "operationId": "doesNotExist"}],
    }
    with pytest.raises(ManifestResolutionError):
        parse_manifest(document, source_file="architecture.yaml", operation_index={})


def test_no_calls_produces_no_relations():
    model = parse_manifest(
        {"service": "order-service"}, source_file="architecture.yaml", operation_index={}
    )
    assert model.relations == []


def test_provenance_recorded():
    model = parse_manifest(
        {"service": "order-service"},
        source_file="architecture.yaml",
        operation_index={},
        source_revision="rev1",
    )
    [provenance] = model.provenance
    assert provenance.source_type == "MANIFEST"
    assert provenance.source_file == "architecture.yaml"
    assert provenance.source_revision == "rev1"


def test_real_manifest_fixture_resolves_against_real_openapi_fixture():
    openapi_document = load_openapi_document(EXAMPLES_DIR / "product-service" / "openapi.yaml")
    openapi_model = parse_openapi(
        openapi_document,
        service_id="product-service",
        source_file="examples/product-service/openapi.yaml",
    )
    operation_index = {
        ("product-service", op.operation_id): op.id
        for op in openapi_model.operations
        if op.operation_id
    }

    manifest_document = load_manifest_document(EXAMPLES_DIR / "order-service" / "architecture.yaml")
    model = parse_manifest(
        manifest_document,
        source_file="examples/order-service/architecture.yaml",
        operation_index=operation_index,
    )
    [relation] = model.relations
    assert relation.type == "CALLS"
    assert relation.source_id == ids.service_id("order-service")
    assert relation.target_id == ids.operation_id("product-service", "GET", "/products/{id}")
