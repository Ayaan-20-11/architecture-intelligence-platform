from enum import StrEnum

from pydantic import BaseModel, Field

from app.provenance.model import Provenance


class Direction(StrEnum):
    SEND = "SEND"
    RECEIVE = "RECEIVE"


class Service(BaseModel):
    id: str
    name: str
    version: str | None = None


class Operation(BaseModel):
    id: str
    service_id: str
    operation_id: str | None = None
    method: str
    path: str
    request_schema_ids: list[str] = Field(default_factory=list)
    response_schema_ids: list[str] = Field(default_factory=list)


class Queue(BaseModel):
    id: str
    name: str
    protocol: str | None = None
    namespace: str | None = None
    queue_type: str = "STANDARD"


class Message(BaseModel):
    id: str
    name: str
    version: str | None = None
    schema_id: str | None = None


class Schema(BaseModel):
    id: str
    name: str
    version: str | None = None
    format: str | None = None
    canonical_hash: str | None = None


class Relation(BaseModel):
    type: str
    source_id: str
    target_id: str


class ArchitectureModel(BaseModel):
    services: list[Service] = Field(default_factory=list)
    operations: list[Operation] = Field(default_factory=list)
    queues: list[Queue] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    schemas: list[Schema] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    provenance: list[Provenance] = Field(default_factory=list)
