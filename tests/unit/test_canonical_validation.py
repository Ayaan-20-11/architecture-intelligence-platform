from pathlib import Path

import pytest
import yaml

from app.canonical.model import (
    ArchitectureModel,
    Message,
    Operation,
    Queue,
    Relation,
    Service,
)
from app.validation.canonical_validation import CanonicalValidationError, validate_canonical_model

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "example_architecture.yaml"


def test_valid_iteration1_fixture_passes():
    data = yaml.safe_load(FIXTURE_PATH.read_text())
    model = ArchitectureModel(**data)
    validate_canonical_model(model)  # must not raise


def test_v1_duplicate_service_id():
    model = ArchitectureModel(
        services=[Service(id="service:a", name="A"), Service(id="service:a", name="A2")]
    )
    with pytest.raises(CanonicalValidationError) as exc:
        validate_canonical_model(model)
    assert "Service id is not unique" in str(exc.value)


def test_v2_operation_without_provider():
    model = ArchitectureModel(
        services=[Service(id="service:a", name="A")],
        operations=[
            Operation(id="operation:a:GET:/x", service_id="service:a", method="GET", path="/x")
        ],
    )
    with pytest.raises(CanonicalValidationError) as exc:
        validate_canonical_model(model)
    assert "exactly one PROVIDES" in str(exc.value)


def test_v2_operation_with_two_providers():
    model = ArchitectureModel(
        services=[Service(id="service:a", name="A"), Service(id="service:b", name="B")],
        operations=[
            Operation(id="operation:a:GET:/x", service_id="service:a", method="GET", path="/x")
        ],
        relations=[
            Relation(type="PROVIDES", source_id="service:a", target_id="operation:a:GET:/x"),
            Relation(type="PROVIDES", source_id="service:b", target_id="operation:a:GET:/x"),
        ],
    )
    with pytest.raises(CanonicalValidationError) as exc:
        validate_canonical_model(model)
    assert "exactly one PROVIDES" in str(exc.value)


def test_v2_provider_mismatch_with_declared_service_id():
    model = ArchitectureModel(
        services=[Service(id="service:a", name="A"), Service(id="service:b", name="B")],
        operations=[
            Operation(id="operation:a:GET:/x", service_id="service:a", method="GET", path="/x")
        ],
        relations=[
            Relation(type="PROVIDES", source_id="service:b", target_id="operation:a:GET:/x")
        ],
    )
    with pytest.raises(CanonicalValidationError) as exc:
        validate_canonical_model(model)
    assert "declares service_id" in str(exc.value)


def test_v3_duplicate_queue_id():
    model = ArchitectureModel(
        queues=[Queue(id="queue:a", name="a"), Queue(id="queue:a", name="a2")]
    )
    with pytest.raises(CanonicalValidationError) as exc:
        validate_canonical_model(model)
    assert "Queue id is not unique" in str(exc.value)


def test_v4_duplicate_message_id():
    model = ArchitectureModel(
        messages=[Message(id="message:a", name="a"), Message(id="message:a", name="a2")]
    )
    with pytest.raises(CanonicalValidationError) as exc:
        validate_canonical_model(model)
    assert "Message id is not unique" in str(exc.value)


def test_v5_calls_unknown_operation():
    model = ArchitectureModel(
        services=[Service(id="service:a", name="A")],
        relations=[Relation(type="CALLS", source_id="service:a", target_id="operation:missing")],
    )
    with pytest.raises(CanonicalValidationError) as exc:
        validate_canonical_model(model)
    assert "unknown operation" in str(exc.value)


def test_v6_response_schema_relation_unknown_schema():
    model = ArchitectureModel(
        services=[Service(id="service:a", name="A")],
        operations=[
            Operation(
                id="operation:a:GET:/x",
                service_id="service:a",
                method="GET",
                path="/x",
                response_schema_ids=["schema:missing"],
            )
        ],
        relations=[
            Relation(type="PROVIDES", source_id="service:a", target_id="operation:a:GET:/x"),
            Relation(
                type="RESPONSE_SCHEMA", source_id="operation:a:GET:/x", target_id="schema:missing"
            ),
        ],
    )
    with pytest.raises(CanonicalValidationError) as exc:
        validate_canonical_model(model)
    assert "unknown schema" in str(exc.value)


def test_v6_message_schema_id_unknown():
    model = ArchitectureModel(
        messages=[Message(id="message:a", name="a", schema_id="schema:missing")]
    )
    with pytest.raises(CanonicalValidationError) as exc:
        validate_canonical_model(model)
    assert "unknown schema" in str(exc.value)


def test_v7_dlq_self_reference():
    model = ArchitectureModel(
        queues=[Queue(id="queue:a", name="a")],
        relations=[Relation(type="DEAD_LETTERS_TO", source_id="queue:a", target_id="queue:a")],
    )
    with pytest.raises(CanonicalValidationError) as exc:
        validate_canonical_model(model)
    assert "cannot be its own DLQ" in str(exc.value)


def test_v8_relation_unknown_source_and_target():
    model = ArchitectureModel(
        relations=[Relation(type="SENDS", source_id="service:missing", target_id="queue:missing")],
    )
    with pytest.raises(CanonicalValidationError) as exc:
        validate_canonical_model(model)
    assert "unknown source" in str(exc.value)
    assert "unknown target" in str(exc.value)


def test_multiple_errors_are_all_reported():
    model = ArchitectureModel(
        services=[Service(id="service:a", name="A"), Service(id="service:a", name="A2")],
        queues=[Queue(id="queue:a", name="a"), Queue(id="queue:a", name="a2")],
    )
    with pytest.raises(CanonicalValidationError) as exc:
        validate_canonical_model(model)
    assert len(exc.value.errors) == 2
