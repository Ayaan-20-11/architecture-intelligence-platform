from pydantic import BaseModel


class Provenance(BaseModel):
    id: str
    source_type: str  # OPENAPI | ASYNCAPI | MANIFEST
    source_file: str
    source_revision: str | None = None
    evidence_type: str = "DECLARED"
