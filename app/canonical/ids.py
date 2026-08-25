def service_id(slug: str) -> str:
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
