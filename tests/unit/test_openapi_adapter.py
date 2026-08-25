import hashlib
import json
from pathlib import Path

from app.canonical import ids
from app.ingestion.openapi_adapter import load_openapi_document, parse_openapi

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"

PRODUCT_SERVICE_DOC = {
    "openapi": "3.1.0",
    "info": {"title": "ProductService", "version": "1.0.0"},
    "paths": {
        "/products/{id}": {
            "get": {
                "operationId": "getProduct",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Product"}}
                        }
                    }
                },
            }
        }
    },
    "components": {
        "schemas": {
            "Product": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
                "required": ["id", "name"],
            }
        }
    },
}


def test_parses_service_metadata():
    model = parse_openapi(
        PRODUCT_SERVICE_DOC,
        service_id="product-service",
        source_file="examples/product-service/openapi.yaml",
    )
    [service] = model.services
    assert service.id == ids.service_id("product-service")
    assert service.name == "ProductService"
    assert service.version == "1.0.0"


def test_parses_operation_matching_spec_example():
    model = parse_openapi(
        PRODUCT_SERVICE_DOC,
        service_id="product-service",
        source_file="examples/product-service/openapi.yaml",
    )
    [operation] = model.operations
    assert operation.id == ids.operation_id("product-service", "GET", "/products/{id}")
    assert operation.operation_id == "getProduct"
    assert operation.method == "GET"
    assert operation.path == "/products/{id}"
    assert operation.response_schema_ids == [ids.schema_id("Product")]
    assert operation.request_schema_ids == []


def test_provides_relation_created():
    model = parse_openapi(
        PRODUCT_SERVICE_DOC,
        service_id="product-service",
        source_file="examples/product-service/openapi.yaml",
    )
    provides = [r for r in model.relations if r.type == "PROVIDES"]
    assert len(provides) == 1
    assert provides[0].source_id == ids.service_id("product-service")
    assert provides[0].target_id == ids.operation_id("product-service", "GET", "/products/{id}")


def test_response_schema_relation_and_canonical_hash():
    model = parse_openapi(
        PRODUCT_SERVICE_DOC,
        service_id="product-service",
        source_file="examples/product-service/openapi.yaml",
    )
    response_schema_relations = [r for r in model.relations if r.type == "RESPONSE_SCHEMA"]
    assert len(response_schema_relations) == 1
    assert response_schema_relations[0].target_id == ids.schema_id("Product")

    [schema] = model.schemas
    assert schema.id == ids.schema_id("Product")
    assert schema.name == "Product"
    assert schema.format == "application/json"
    expected_hash = hashlib.sha256(
        json.dumps(PRODUCT_SERVICE_DOC["components"]["schemas"]["Product"], sort_keys=True).encode(
            "utf-8"
        )
    ).hexdigest()
    assert schema.canonical_hash == expected_hash


def test_provenance_recorded():
    model = parse_openapi(
        PRODUCT_SERVICE_DOC,
        service_id="product-service",
        source_file="examples/product-service/openapi.yaml",
        source_revision="abc123",
    )
    [provenance] = model.provenance
    assert provenance.source_type == "OPENAPI"
    assert provenance.source_file == "examples/product-service/openapi.yaml"
    assert provenance.source_revision == "abc123"
    assert provenance.evidence_type == "DECLARED"


def test_service_with_no_operations_still_produces_service_and_provenance():
    document = {"openapi": "3.1.0", "info": {"title": "PaymentService"}, "paths": {}}
    model = parse_openapi(
        document, service_id="payment-service", source_file="examples/payment-service/openapi.yaml"
    )
    assert len(model.services) == 1
    assert model.operations == []
    assert model.schemas == []
    assert model.relations == []
    assert len(model.provenance) == 1


def test_request_body_and_schema_dedup_across_operations():
    document = {
        "openapi": "3.1.0",
        "info": {"title": "OrderService", "version": "1.0.0"},
        "paths": {
            "/orders": {
                "post": {
                    "operationId": "createOrder",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OrderRequest"}
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Order"}
                                }
                            }
                        }
                    },
                }
            },
            "/orders/{id}": {
                "get": {
                    "operationId": "getOrder",
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Order"}
                                }
                            }
                        }
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "OrderRequest": {"type": "object"},
                "Order": {"type": "object"},
            }
        },
    }
    model = parse_openapi(
        document, service_id="order-service", source_file="examples/order-service/openapi.yaml"
    )

    assert len(model.operations) == 2
    # Order is referenced by two different operations but must only be
    # materialized once in the deduped schema list.
    assert {s.name for s in model.schemas} == {"OrderRequest", "Order"}

    create_order = next(op for op in model.operations if op.operation_id == "createOrder")
    assert create_order.request_schema_ids == [ids.schema_id("OrderRequest")]
    assert create_order.response_schema_ids == [ids.schema_id("Order")]

    get_order = next(op for op in model.operations if op.operation_id == "getOrder")
    assert get_order.response_schema_ids == [ids.schema_id("Order")]

    provides = [r for r in model.relations if r.type == "PROVIDES"]
    assert len(provides) == 2


def test_loads_and_parses_real_product_service_fixture():
    document = load_openapi_document(EXAMPLES_DIR / "product-service" / "openapi.yaml")
    model = parse_openapi(
        document, service_id="product-service", source_file="examples/product-service/openapi.yaml"
    )
    [operation] = model.operations
    assert operation.operation_id == "getProduct"
    assert operation.response_schema_ids == [ids.schema_id("Product")]


def test_loads_and_parses_real_order_service_fixture():
    document = load_openapi_document(EXAMPLES_DIR / "order-service" / "openapi.yaml")
    model = parse_openapi(
        document, service_id="order-service", source_file="examples/order-service/openapi.yaml"
    )
    assert len(model.operations) == 2
    assert {s.name for s in model.schemas} == {"OrderRequest", "Order"}
