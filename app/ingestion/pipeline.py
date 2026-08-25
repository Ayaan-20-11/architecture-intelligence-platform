from collections import defaultdict
from pathlib import Path

from app.canonical.model import ArchitectureModel, Message, Operation, Queue, Schema, Service
from app.ingestion.asyncapi_adapter import load_asyncapi_document, parse_asyncapi
from app.ingestion.manifest_adapter import load_manifest_document, parse_manifest
from app.ingestion.openapi_adapter import load_openapi_document, parse_openapi
from app.ingestion.scanner import SpecificationType, scan_directory
from app.provenance.model import Provenance
from app.validation.canonical_validation import validate_canonical_model
from app.validation.source_validation import (
    validate_asyncapi_document,
    validate_manifest_document,
    validate_openapi_document,
)


def merge_models(models: list[ArchitectureModel]) -> ArchitectureModel:
    """Combines partial models from multiple adapters/sources, deduping entities by id (first wins)."""
    services: dict[str, Service] = {}
    operations: dict[str, Operation] = {}
    queues: dict[str, Queue] = {}
    messages: dict[str, Message] = {}
    schemas: dict[str, Schema] = {}
    relations = []
    seen_relations: set[tuple[str, str, str]] = set()
    provenance: list[Provenance] = []

    for model in models:
        for service in model.services:
            services.setdefault(service.id, service)
        for operation in model.operations:
            operations.setdefault(operation.id, operation)
        for queue in model.queues:
            queues.setdefault(queue.id, queue)
        for message in model.messages:
            messages.setdefault(message.id, message)
        for schema in model.schemas:
            schemas.setdefault(schema.id, schema)
        for relation in model.relations:
            key = (relation.type, relation.source_id, relation.target_id)
            if key not in seen_relations:
                seen_relations.add(key)
                relations.append(relation)
        provenance.extend(model.provenance)

    return ArchitectureModel(
        services=list(services.values()),
        operations=list(operations.values()),
        queues=list(queues.values()),
        messages=list(messages.values()),
        schemas=list(schemas.values()),
        relations=relations,
        provenance=provenance,
    )


def parse_sources(root: Path) -> dict[str, ArchitectureModel]:
    """Scans, source-validates, and parses every source into one merged ArchitectureModel per service_id (spec §5.2); the importer needs this per-service scoping for §12.2 reimport."""
    sources = scan_directory(root)

    openapi_sources = [s for s in sources if s.type == SpecificationType.OPENAPI]
    asyncapi_sources = [s for s in sources if s.type == SpecificationType.ASYNCAPI]
    manifest_sources = [s for s in sources if s.type == SpecificationType.MANIFEST]

    partials_by_service: dict[str, list[ArchitectureModel]] = defaultdict(list)
    operation_index: dict[tuple[str, str], str] = {}

    for source in openapi_sources:
        document = load_openapi_document(source.path)
        validate_openapi_document(document, source_file=str(source.path))
        model = parse_openapi(
            document,
            service_id=source.service_id,
            source_file=str(source.path),
            source_revision=source.revision,
        )
        partials_by_service[source.service_id].append(model)
        for operation in model.operations:
            if operation.operation_id:
                operation_index[(source.service_id, operation.operation_id)] = operation.id

    for source in asyncapi_sources:
        document = load_asyncapi_document(source.path)
        validate_asyncapi_document(document, source_file=str(source.path))
        partials_by_service[source.service_id].append(
            parse_asyncapi(
                document,
                service_id=source.service_id,
                source_file=str(source.path),
                source_revision=source.revision,
            )
        )

    for source in manifest_sources:
        document = load_manifest_document(source.path)
        validate_manifest_document(document, source_file=str(source.path))
        partials_by_service[source.service_id].append(
            parse_manifest(
                document,
                source_file=str(source.path),
                operation_index=operation_index,
                source_revision=source.revision,
            )
        )

    return {service_id: merge_models(models) for service_id, models in partials_by_service.items()}


def import_sources(root: Path) -> ArchitectureModel:
    """Runs scan -> parse -> source-validate -> map -> merge -> canonical-validate (spec §5.2); raises without returning a partial model on any failure (V9/AC14)."""
    merged = merge_models(list(parse_sources(root).values()))
    validate_canonical_model(merged)
    return merged
