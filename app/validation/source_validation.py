from collections.abc import Iterator

from jsonschema import Draft202012Validator

OPENAPI_SCHEMA = {
    "type": "object",
    "required": ["openapi", "info", "paths"],
    "properties": {
        "openapi": {"type": "string"},
        "info": {
            "type": "object",
            "required": ["title"],
            "properties": {"title": {"type": "string"}},
        },
        "paths": {"type": "object"},
    },
}

ASYNCAPI_SCHEMA = {
    "type": "object",
    "required": ["asyncapi", "info", "channels"],
    "properties": {
        "asyncapi": {"type": "string"},
        "info": {
            "type": "object",
            "required": ["title"],
            "properties": {"title": {"type": "string"}},
        },
        "channels": {"type": "object"},
    },
}

MANIFEST_SCHEMA = {
    "type": "object",
    "required": ["service"],
    "properties": {
        "service": {"type": "string"},
        "calls": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["service", "operationId"],
                "properties": {"service": {"type": "string"}, "operationId": {"type": "string"}},
            },
        },
    },
}


class SourceValidationError(ValueError):
    def __init__(self, source_file: str, errors: list[str]):
        self.source_file = source_file
        self.errors = errors
        super().__init__(f"{source_file}: {'; '.join(errors)}")


def _structural_errors(document: dict, schema: dict) -> list[str]:
    validator = Draft202012Validator(schema)
    return [
        error.message
        for error in sorted(validator.iter_errors(document), key=lambda e: list(e.path))
    ]


def _iter_refs(node: object) -> Iterator[str]:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            yield ref
        for value in node.values():
            yield from _iter_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_refs(item)


def _ref_resolves(ref: str, document: dict) -> bool:
    node: object = document
    try:
        for part in ref.lstrip("#/").split("/"):
            node = node[part]  # type: ignore[index]
    except (KeyError, TypeError, IndexError):
        return False
    return True


def _dangling_ref_errors(document: dict) -> list[str]:
    errors = []
    for ref in _iter_refs(document):
        if not ref.startswith("#/"):
            errors.append(
                f"unsupported external $ref (only local refs are supported in the PoC): {ref}"
            )
        elif not _ref_resolves(ref, document):
            errors.append(f"dangling $ref: {ref}")
    return errors


def validate_openapi_document(document: dict, *, source_file: str) -> None:
    errors = _structural_errors(document, OPENAPI_SCHEMA) + _dangling_ref_errors(document)
    if errors:
        raise SourceValidationError(source_file, errors)


def validate_asyncapi_document(document: dict, *, source_file: str) -> None:
    errors = _structural_errors(document, ASYNCAPI_SCHEMA) + _dangling_ref_errors(document)
    if errors:
        raise SourceValidationError(source_file, errors)


def validate_manifest_document(document: dict, *, source_file: str) -> None:
    errors = _structural_errors(document, MANIFEST_SCHEMA)
    if errors:
        raise SourceValidationError(source_file, errors)
