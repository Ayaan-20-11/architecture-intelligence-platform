import hashlib
import json
from pathlib import Path

import yaml

from app.canonical import ids
from app.canonical.model import (
    ArchitectureModel,
    Direction,
    Message,
    Queue,
    Relation,
    Schema,
    Service,
)
from app.provenance.model import Provenance

# AsyncAPI 2.x: "publish" = the described application sends on the channel,
# "subscribe" = it receives from the channel (named from the app's own
# perspective, not the client's - a common source of confusion).
OPERATION_DIRECTIONS = {"publish": Direction.SEND, "subscribe": Direction.RECEIVE}
RELATION_TYPES = {Direction.SEND: "SENDS", Direction.RECEIVE: "RECEIVES_FROM"}


def load_asyncapi_document(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _resolve_ref(ref: str, document: dict) -> dict:
    node = document
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def _extract_message_defs(operation_def: dict, document: dict) -> list[dict]:
    message_obj = operation_def.get("message")
    if not message_obj:
        return []
    candidates = message_obj.get("oneOf", [message_obj])
    return [_resolve_ref(m["$ref"], document) if "$ref" in m else m for m in candidates]


def _resolve_schema_definition(payload: dict | None, document: dict) -> dict | None:
    if not payload:
        return None
    return _resolve_ref(payload["$ref"], document) if "$ref" in payload else payload


def parse_asyncapi(
    document: dict,
    *,
    service_id: str,
    source_file: str,
    source_revision: str | None = None,
) -> ArchitectureModel:
    """Maps AsyncAPI queue channels (spec §7) to Queue/Message/Schema entities."""
    full_service_id = ids.service_id(service_id)
    info = document.get("info") or {}
    service = Service(
        id=full_service_id, name=info.get("title", service_id), version=info.get("version")
    )

    channels = document.get("channels") or {}
    queues_by_id: dict[str, Queue] = {}
    messages_by_id: dict[str, Message] = {}
    schemas_by_id: dict[str, Schema] = {}
    relations: list[Relation] = []
    seen_relations: set[tuple[str, str, str]] = set()

    def add_relation(relation_type: str, source_id: str, target_id: str) -> None:
        key = (relation_type, source_id, target_id)
        if key not in seen_relations:
            seen_relations.add(key)
            relations.append(Relation(type=relation_type, source_id=source_id, target_id=target_id))

    dlq_links: list[tuple[str, str]] = []
    for channel_name, channel_def in channels.items():
        if not isinstance(channel_def, dict):
            continue
        bindings = channel_def.get("bindings") or {}
        protocol = next(iter(bindings), None)
        namespace = channel_def.get("x-namespace")
        queue_id_value = ids.queue_id(channel_name, namespace=namespace)
        queues_by_id[queue_id_value] = Queue(
            id=queue_id_value, name=channel_name, protocol=protocol, namespace=namespace
        )

        dlq_channel_name = channel_def.get("x-dead-letter-queue")
        if dlq_channel_name:
            dlq_links.append((queue_id_value, ids.queue_id(dlq_channel_name, namespace=namespace)))

    for source_id, target_id in dlq_links:
        if target_id not in queues_by_id:
            queues_by_id[target_id] = Queue(id=target_id, name=target_id.rsplit(":", 1)[-1])
        add_relation("DEAD_LETTERS_TO", source_id, target_id)

    for channel_name, channel_def in channels.items():
        if not isinstance(channel_def, dict):
            continue
        namespace = channel_def.get("x-namespace")
        queue_id_value = ids.queue_id(channel_name, namespace=namespace)

        for operation_key, direction in OPERATION_DIRECTIONS.items():
            operation_def = channel_def.get(operation_key)
            if not isinstance(operation_def, dict):
                continue
            add_relation(RELATION_TYPES[direction], full_service_id, queue_id_value)

            for message_def in _extract_message_defs(operation_def, document):
                message_name = message_def.get("name") or message_def.get("title")
                if not message_name:
                    continue
                message_version = message_def.get("x-version")
                message_id_value = ids.message_id(message_name, message_version)
                schema_id_value = ids.schema_id(message_name, message_version)

                if message_id_value not in messages_by_id:
                    messages_by_id[message_id_value] = Message(
                        id=message_id_value,
                        name=message_name,
                        version=message_version,
                        schema_id=schema_id_value,
                    )
                add_relation("CARRIES", queue_id_value, message_id_value)

                if schema_id_value not in schemas_by_id:
                    definition = _resolve_schema_definition(message_def.get("payload"), document)
                    canonical_hash = (
                        hashlib.sha256(
                            json.dumps(definition, sort_keys=True).encode("utf-8")
                        ).hexdigest()
                        if definition is not None
                        else None
                    )
                    schemas_by_id[schema_id_value] = Schema(
                        id=schema_id_value,
                        name=message_name,
                        version=message_version,
                        format="application/json",
                        canonical_hash=canonical_hash,
                    )
                add_relation("CONFORMS_TO", message_id_value, schema_id_value)

    evidence = Provenance(
        id=ids.evidence_id("ASYNCAPI", service_id, source_revision),
        source_type="ASYNCAPI",
        source_file=source_file,
        source_revision=source_revision,
    )
    relations = [r.model_copy(update={"evidence_ids": [evidence.id]}) for r in relations]

    return ArchitectureModel(
        services=[service],
        queues=list(queues_by_id.values()),
        messages=list(messages_by_id.values()),
        schemas=list(schemas_by_id.values()),
        relations=relations,
        provenance=[evidence],
    )
