from pathlib import Path

import pytest
import yaml

from app.ingestion.scanner import SpecificationType, scan_directory
from app.validation.source_validation import (
    SourceValidationError,
    validate_asyncapi_document,
    validate_manifest_document,
    validate_openapi_document,
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"

VALID_OPENAPI_DOC = {
    "openapi": "3.1.0",
    "info": {"title": "X"},
    "paths": {
        "/x": {
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/X"}}
                        }
                    }
                }
            }
        }
    },
    "components": {"schemas": {"X": {"type": "object"}}},
}

VALID_ASYNCAPI_DOC = {
    "asyncapi": "2.6.0",
    "info": {"title": "X"},
    "channels": {"x-q": {"publish": {"message": {"$ref": "#/components/messages/X"}}}},
    "components": {"messages": {"X": {"name": "X"}}},
}

VALID_MANIFEST_DOC = {
    "service": "order-service",
    "calls": [{"service": "product-service", "operationId": "getProduct"}],
}


def test_valid_openapi_document_passes():
    validate_openapi_document(VALID_OPENAPI_DOC, source_file="openapi.yaml")


def test_openapi_missing_required_field_raises():
    with pytest.raises(SourceValidationError):
        validate_openapi_document({"openapi": "3.1.0", "paths": {}}, source_file="openapi.yaml")


def test_openapi_dangling_ref_raises():
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "X"},
        "paths": {
            "/x": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Missing"}
                                }
                            }
                        }
                    }
                }
            }
        },
    }
    with pytest.raises(SourceValidationError) as exc:
        validate_openapi_document(doc, source_file="openapi.yaml")
    assert "dangling" in str(exc.value)


def test_openapi_external_ref_rejected():
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "X"},
        "paths": {
            "/x": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {"schema": {"$ref": "other-file.yaml#/Foo"}}
                            }
                        }
                    }
                }
            }
        },
    }
    with pytest.raises(SourceValidationError) as exc:
        validate_openapi_document(doc, source_file="openapi.yaml")
    assert "external" in str(exc.value)


def test_valid_asyncapi_document_passes():
    validate_asyncapi_document(VALID_ASYNCAPI_DOC, source_file="asyncapi.yaml")


def test_asyncapi_missing_required_field_raises():
    with pytest.raises(SourceValidationError):
        validate_asyncapi_document(
            {"asyncapi": "2.6.0", "channels": {}}, source_file="asyncapi.yaml"
        )


def test_asyncapi_dangling_ref_raises():
    doc = {
        "asyncapi": "2.6.0",
        "info": {"title": "X"},
        "channels": {"x-q": {"publish": {"message": {"$ref": "#/components/messages/Missing"}}}},
    }
    with pytest.raises(SourceValidationError) as exc:
        validate_asyncapi_document(doc, source_file="asyncapi.yaml")
    assert "dangling" in str(exc.value)


def test_valid_manifest_document_passes():
    validate_manifest_document(VALID_MANIFEST_DOC, source_file="architecture.yaml")


def test_manifest_missing_service_raises():
    with pytest.raises(SourceValidationError):
        validate_manifest_document({"calls": []}, source_file="architecture.yaml")


def test_manifest_call_entry_missing_operation_id_raises():
    doc = {"service": "order-service", "calls": [{"service": "product-service"}]}
    with pytest.raises(SourceValidationError):
        validate_manifest_document(doc, source_file="architecture.yaml")


def test_real_example_fixtures_all_pass_source_validation():
    for source in scan_directory(EXAMPLES_DIR):
        document = yaml.safe_load(source.path.read_text())
        if source.type == SpecificationType.OPENAPI:
            validate_openapi_document(document, source_file=str(source.path))
        elif source.type == SpecificationType.ASYNCAPI:
            validate_asyncapi_document(document, source_file=str(source.path))
        else:
            validate_manifest_document(document, source_file=str(source.path))
