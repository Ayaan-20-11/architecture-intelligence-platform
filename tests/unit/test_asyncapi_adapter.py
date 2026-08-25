import hashlib
import json
from pathlib import Path

from app.canonical import ids
from app.ingestion.asyncapi_adapter import load_asyncapi_document, parse_asyncapi

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"

# Matches the spec §7.1 target model exactly:
# OrderService -SENDS-> payment-q -CARRIES-> PaymentRequested -CONFORMS_TO-> PaymentRequestedSchema:v2
ORDER_SERVICE_DOC = {
    "asyncapi": "2.6.0",
    "info": {"title": "OrderService", "version": "1.0.0"},
    "channels": {
        "payment-q": {
            "publish": {
                "operationId": "sendPaymentRequested",
                "message": {"$ref": "#/components/messages/PaymentRequested"},
            }
        }
    },
    "components": {
        "messages": {
            "PaymentRequested": {
                "name": "PaymentRequested",
                "x-version": "v2",
                "payload": {"$ref": "#/components/schemas/PaymentRequestedPayload"},
            }
        },
        "schemas": {
            "PaymentRequestedPayload": {
                "type": "object",
                "properties": {"orderId": {"type": "string"}},
                "required": ["orderId"],
            }
        },
    },
}

# Matches spec §7.1: PaymentService -RECEIVES_FROM-> payment-q
PAYMENT_SERVICE_DOC = {
    "asyncapi": "2.6.0",
    "info": {"title": "PaymentService", "version": "1.0.0"},
    "channels": {
        "payment-q": {
            "x-dead-letter-queue": "payment-dlq",
            "subscribe": {
                "operationId": "receivePaymentRequested",
                "message": {"$ref": "#/components/messages/PaymentRequested"},
            },
        }
    },
    "components": {
        "messages": {
            "PaymentRequested": {
                "name": "PaymentRequested",
                "x-version": "v2",
                "payload": {"$ref": "#/components/schemas/PaymentRequestedPayload"},
            }
        },
        "schemas": {
            "PaymentRequestedPayload": {
                "type": "object",
                "properties": {"orderId": {"type": "string"}},
                "required": ["orderId"],
            }
        },
    },
}


def test_parses_service_metadata():
    model = parse_asyncapi(
        ORDER_SERVICE_DOC,
        service_id="order-service",
        source_file="examples/order-service/asyncapi.yaml",
    )
    [service] = model.services
    assert service.id == ids.service_id("order-service")
    assert service.name == "OrderService"
    assert service.version == "1.0.0"


def test_publish_creates_sends_relation_and_queue():
    model = parse_asyncapi(
        ORDER_SERVICE_DOC,
        service_id="order-service",
        source_file="examples/order-service/asyncapi.yaml",
    )
    [queue] = model.queues
    assert queue.id == ids.queue_id("payment-q")
    assert queue.name == "payment-q"

    sends = [r for r in model.relations if r.type == "SENDS"]
    assert len(sends) == 1
    assert sends[0].source_id == ids.service_id("order-service")
    assert sends[0].target_id == ids.queue_id("payment-q")


def test_carries_and_conforms_to_relations_with_message_version():
    model = parse_asyncapi(
        ORDER_SERVICE_DOC,
        service_id="order-service",
        source_file="examples/order-service/asyncapi.yaml",
    )
    expected_message_id = ids.message_id("PaymentRequested", "v2")
    expected_schema_id = ids.schema_id("PaymentRequested", "v2")

    [message] = model.messages
    assert message.id == expected_message_id
    assert message.version == "v2"
    assert message.schema_id == expected_schema_id

    carries = [r for r in model.relations if r.type == "CARRIES"]
    assert len(carries) == 1
    assert carries[0].source_id == ids.queue_id("payment-q")
    assert carries[0].target_id == expected_message_id

    conforms_to = [r for r in model.relations if r.type == "CONFORMS_TO"]
    assert len(conforms_to) == 1
    assert conforms_to[0].source_id == expected_message_id
    assert conforms_to[0].target_id == expected_schema_id


def test_schema_canonical_hash_matches_payload_definition():
    model = parse_asyncapi(
        ORDER_SERVICE_DOC,
        service_id="order-service",
        source_file="examples/order-service/asyncapi.yaml",
    )
    [schema] = model.schemas
    assert schema.id == ids.schema_id("PaymentRequested", "v2")
    assert schema.format == "application/json"
    expected_hash = hashlib.sha256(
        json.dumps(
            ORDER_SERVICE_DOC["components"]["schemas"]["PaymentRequestedPayload"], sort_keys=True
        ).encode("utf-8")
    ).hexdigest()
    assert schema.canonical_hash == expected_hash


def test_subscribe_creates_receives_from_relation():
    model = parse_asyncapi(
        PAYMENT_SERVICE_DOC,
        service_id="payment-service",
        source_file="examples/payment-service/asyncapi.yaml",
    )
    receives = [r for r in model.relations if r.type == "RECEIVES_FROM"]
    assert len(receives) == 1
    assert receives[0].source_id == ids.service_id("payment-service")
    assert receives[0].target_id == ids.queue_id("payment-q")


def test_dead_letters_to_relation_and_stub_queue_for_undeclared_dlq():
    model = parse_asyncapi(
        PAYMENT_SERVICE_DOC,
        service_id="payment-service",
        source_file="examples/payment-service/asyncapi.yaml",
    )
    dead_letters = [r for r in model.relations if r.type == "DEAD_LETTERS_TO"]
    assert len(dead_letters) == 1
    assert dead_letters[0].source_id == ids.queue_id("payment-q")
    assert dead_letters[0].target_id == ids.queue_id("payment-dlq")

    dlq_queue = next(q for q in model.queues if q.id == ids.queue_id("payment-dlq"))
    assert dlq_queue.name == "payment-dlq"


def test_protocol_extracted_from_bindings():
    document = {
        "asyncapi": "2.6.0",
        "info": {"title": "OrderService"},
        "channels": {
            "payment-q": {
                "bindings": {"amqp": {"is": "queue"}},
                "publish": {"message": {"name": "PaymentRequested"}},
            }
        },
    }
    model = parse_asyncapi(
        document, service_id="order-service", source_file="examples/order-service/asyncapi.yaml"
    )
    [queue] = model.queues
    assert queue.protocol == "amqp"


def test_namespace_matches_spec_example_id_format():
    document = {
        "asyncapi": "2.6.0",
        "info": {"title": "OrderService"},
        "channels": {
            "payment-q": {
                "x-namespace": "asb:commerce",
                "publish": {"message": {"name": "PaymentRequested"}},
            }
        },
    }
    model = parse_asyncapi(
        document, service_id="order-service", source_file="examples/order-service/asyncapi.yaml"
    )
    [queue] = model.queues
    assert queue.id == "queue:asb:commerce:payment-q"
    assert queue.namespace == "asb:commerce"


def test_one_of_multiple_messages_on_one_operation():
    document = {
        "asyncapi": "2.6.0",
        "info": {"title": "OrderService"},
        "channels": {
            "order-events-q": {
                "publish": {
                    "message": {
                        "oneOf": [
                            {"$ref": "#/components/messages/OrderCreated"},
                            {"$ref": "#/components/messages/OrderCancelled"},
                        ]
                    }
                }
            }
        },
        "components": {
            "messages": {
                "OrderCreated": {"name": "OrderCreated"},
                "OrderCancelled": {"name": "OrderCancelled"},
            }
        },
    }
    model = parse_asyncapi(
        document, service_id="order-service", source_file="examples/order-service/asyncapi.yaml"
    )
    assert {m.name for m in model.messages} == {"OrderCreated", "OrderCancelled"}
    carries = [r for r in model.relations if r.type == "CARRIES"]
    assert len(carries) == 2


def test_provenance_recorded():
    model = parse_asyncapi(
        ORDER_SERVICE_DOC,
        service_id="order-service",
        source_file="examples/order-service/asyncapi.yaml",
        source_revision="abc123",
    )
    [provenance] = model.provenance
    assert provenance.source_type == "ASYNCAPI"
    assert provenance.source_file == "examples/order-service/asyncapi.yaml"
    assert provenance.source_revision == "abc123"


def test_real_fixtures_produce_consistent_ids_across_producer_and_consumer():
    order_model = parse_asyncapi(
        load_asyncapi_document(EXAMPLES_DIR / "order-service" / "asyncapi.yaml"),
        service_id="order-service",
        source_file="examples/order-service/asyncapi.yaml",
    )
    payment_model = parse_asyncapi(
        load_asyncapi_document(EXAMPLES_DIR / "payment-service" / "asyncapi.yaml"),
        service_id="payment-service",
        source_file="examples/payment-service/asyncapi.yaml",
    )

    order_payment_message = next(m for m in order_model.messages if m.name == "PaymentRequested")
    payment_payment_message = next(
        m for m in payment_model.messages if m.name == "PaymentRequested"
    )
    assert order_payment_message.id == payment_payment_message.id
    assert order_payment_message.schema_id == payment_payment_message.schema_id

    order_queue = next(q for q in order_model.queues if q.name == "payment-q")
    payment_queue = next(q for q in payment_model.queues if q.name == "payment-q")
    assert order_queue.id == payment_queue.id


def test_real_invoice_service_fixture():
    document = load_asyncapi_document(EXAMPLES_DIR / "invoice-service" / "asyncapi.yaml")
    model = parse_asyncapi(
        document, service_id="invoice-service", source_file="examples/invoice-service/asyncapi.yaml"
    )
    receives = [r for r in model.relations if r.type == "RECEIVES_FROM"]
    assert len(receives) == 1
    assert receives[0].target_id == ids.queue_id("invoice-q")
    [message] = model.messages
    assert message.id == ids.message_id("InvoiceCreated", "v1")


def test_real_payment_service_fixture_has_all_three_channels():
    document = load_asyncapi_document(EXAMPLES_DIR / "payment-service" / "asyncapi.yaml")
    model = parse_asyncapi(
        document, service_id="payment-service", source_file="examples/payment-service/asyncapi.yaml"
    )
    queue_names = {q.name for q in model.queues}
    assert queue_names == {"payment-q", "invoice-q", "unknown-producer-q", "payment-dlq"}

    sends = {r.target_id for r in model.relations if r.type == "SENDS"}
    receives = {r.target_id for r in model.relations if r.type == "RECEIVES_FROM"}
    assert sends == {ids.queue_id("invoice-q")}
    assert receives == {ids.queue_id("payment-q"), ids.queue_id("unknown-producer-q")}
