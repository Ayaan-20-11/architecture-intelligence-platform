from pathlib import Path

import yaml

from app.canonical import ids
from app.canonical.model import ArchitectureModel, Relation
from app.provenance.model import Provenance


class ManifestResolutionError(ValueError):
    """Raised when a manifest references an operationId unknown to the scanned OpenAPI sources."""

    def __init__(self, *, source_file: str, service: str, operation_id: str):
        self.source_file = source_file
        self.service = service
        self.operation_id = operation_id
        super().__init__(
            f"{source_file}: service '{service}' has no known operationId '{operation_id}' "
            "among the scanned OpenAPI sources"
        )


def load_manifest_document(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def parse_manifest(
    document: dict,
    *,
    source_file: str,
    operation_index: dict[tuple[str, str], str],
    source_revision: str | None = None,
) -> ArchitectureModel:
    """Maps architecture.yaml calls (spec §8) to CALLS relations via operation_index."""
    caller_service_id = ids.service_id(document["service"])

    relations: list[Relation] = []
    for entry in document.get("calls") or []:
        target_service_slug = entry["service"]
        operation_id_name = entry["operationId"]
        target_operation_id = operation_index.get((target_service_slug, operation_id_name))
        if target_operation_id is None:
            raise ManifestResolutionError(
                source_file=source_file, service=target_service_slug, operation_id=operation_id_name
            )
        relations.append(
            Relation(type="CALLS", source_id=caller_service_id, target_id=target_operation_id)
        )

    return ArchitectureModel(
        relations=relations,
        provenance=[
            Provenance(
                source_type="MANIFEST", source_file=source_file, source_revision=source_revision
            )
        ],
    )
