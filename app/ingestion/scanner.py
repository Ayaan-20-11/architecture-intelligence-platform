from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel


class SpecificationType(StrEnum):
    OPENAPI = "OPENAPI"
    ASYNCAPI = "ASYNCAPI"
    MANIFEST = "MANIFEST"


class SpecificationSource(BaseModel):
    path: Path
    type: SpecificationType
    service_id: str
    revision: str | None = None


FILE_KIND_BY_NAME = {
    "openapi.yaml": SpecificationType.OPENAPI,
    "openapi.yml": SpecificationType.OPENAPI,
    "openapi.json": SpecificationType.OPENAPI,
    "asyncapi.yaml": SpecificationType.ASYNCAPI,
    "asyncapi.yml": SpecificationType.ASYNCAPI,
    "asyncapi.json": SpecificationType.ASYNCAPI,
    "architecture.yaml": SpecificationType.MANIFEST,
}


def scan_directory(root: Path) -> list[SpecificationSource]:
    """Finds spec files under root/{service}/ subdirectories (spec §5.1)."""
    sources: list[SpecificationSource] = []
    for service_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for filename, spec_type in FILE_KIND_BY_NAME.items():
            candidate = service_dir / filename
            if candidate.is_file():
                sources.append(
                    SpecificationSource(path=candidate, type=spec_type, service_id=service_dir.name)
                )
    return sources
