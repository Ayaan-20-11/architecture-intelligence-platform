import hashlib
import json
from pathlib import Path

import yaml

from app.canonical import ids
from app.canonical.model import ArchitectureModel, Operation, Relation, Schema, Service
from app.provenance.model import Provenance

HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def load_openapi_document(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def parse_openapi(
    document: dict,
    *,
    service_id: str,
    source_file: str,
    source_revision: str | None = None,
) -> ArchitectureModel:
    """Maps OpenAPI provider info (spec §6) to Service/Operation/Schema entities."""
    full_service_id = ids.service_id(service_id)
    info = document.get("info") or {}
    service = Service(
        id=full_service_id, name=info.get("title", service_id), version=info.get("version")
    )

    components_schemas = ((document.get("components") or {}).get("schemas")) or {}
    schemas_by_name: dict[str, Schema] = {}

    def resolve_schema_ref(schema_obj: dict | None, media_type: str | None) -> str | None:
        if not schema_obj:
            return None
        ref = schema_obj.get("$ref")
        if not ref:
            return None
        name = ref.rsplit("/", 1)[-1]
        if name not in schemas_by_name:
            definition = components_schemas.get(name)
            canonical_hash = (
                hashlib.sha256(json.dumps(definition, sort_keys=True).encode("utf-8")).hexdigest()
                if definition is not None
                else None
            )
            schemas_by_name[name] = Schema(
                id=ids.schema_id(name),
                name=name,
                format=media_type,
                canonical_hash=canonical_hash,
            )
        return schemas_by_name[name].id

    operations: list[Operation] = []
    relations: list[Relation] = []

    for path, path_item in (document.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, op in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(op, dict):
                continue

            operation_id_value = ids.operation_id(service_id, method, path)

            request_schema_ids: list[str] = []
            request_content = ((op.get("requestBody") or {}).get("content")) or {}
            for media_type, media_obj in request_content.items():
                schema_id_value = resolve_schema_ref(media_obj.get("schema"), media_type)
                if schema_id_value and schema_id_value not in request_schema_ids:
                    request_schema_ids.append(schema_id_value)

            response_schema_ids: list[str] = []
            for response_obj in (op.get("responses") or {}).values():
                if not isinstance(response_obj, dict):
                    continue
                for media_type, media_obj in (response_obj.get("content") or {}).items():
                    schema_id_value = resolve_schema_ref(media_obj.get("schema"), media_type)
                    if schema_id_value and schema_id_value not in response_schema_ids:
                        response_schema_ids.append(schema_id_value)

            operations.append(
                Operation(
                    id=operation_id_value,
                    service_id=full_service_id,
                    operation_id=op.get("operationId"),
                    method=method.upper(),
                    path=path,
                    request_schema_ids=request_schema_ids,
                    response_schema_ids=response_schema_ids,
                )
            )
            relations.append(
                Relation(type="PROVIDES", source_id=full_service_id, target_id=operation_id_value)
            )
            relations.extend(
                Relation(
                    type="REQUEST_SCHEMA", source_id=operation_id_value, target_id=schema_id_value
                )
                for schema_id_value in request_schema_ids
            )
            relations.extend(
                Relation(
                    type="RESPONSE_SCHEMA", source_id=operation_id_value, target_id=schema_id_value
                )
                for schema_id_value in response_schema_ids
            )

    return ArchitectureModel(
        services=[service],
        operations=operations,
        schemas=list(schemas_by_name.values()),
        relations=relations,
        provenance=[
            Provenance(
                source_type="OPENAPI", source_file=source_file, source_revision=source_revision
            )
        ],
    )
