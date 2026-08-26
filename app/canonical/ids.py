import hashlib
from datetime import datetime


def service_id(slug: str, namespace: str | None = None) -> str:
    if namespace:
        return f"service:{namespace}:{slug}"
    return f"service:{slug}"


def operation_id(service_slug: str, method: str, path: str) -> str:
    return f"operation:{service_slug}:{method.upper()}:{path}"


def queue_id(name: str, namespace: str | None = None) -> str:
    if namespace:
        return f"queue:{namespace}:{name}"
    return f"queue:{name}"


def message_id(name: str, version: str | None = None) -> str:
    if version:
        return f"message:{name}:{version}"
    return f"message:{name}"


def schema_id(name: str, version: str | None = None) -> str:
    if version:
        return f"schema:{name}:{version}"
    return f"schema:{name}"


def evidence_id(source_type: str, service_slug: str, revision: str | None = None) -> str:
    if revision:
        return f"evidence:{source_type.lower()}:{service_slug}:{revision}"
    return f"evidence:{source_type.lower()}:{service_slug}"


def observed_evidence_id(
    environment: str, bucket_start: datetime, subject_id: str, relation_type: str, object_id: str
) -> str:
    """Deterministic id for an OTel-observed evidence bucket (spec §17). Has no trace/span-specific
    component - every seed for the same (fact, day, environment) gets the identical id, so a later
    Aggregator can MERGE into it rather than searching for a match."""
    fact_hash = hashlib.sha256(f"{subject_id}|{relation_type}|{object_id}".encode()).hexdigest()[
        :12
    ]
    return f"evidence:otel:{environment}:{bucket_start:%Y-%m-%d}:{fact_hash}"
