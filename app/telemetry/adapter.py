from app.canonical import ids
from app.provenance.model import ObservedEvidence
from app.telemetry.model import (
    DiscoveryStatus,
    ObservationBatch,
    ObservedFactCandidate,
    ObservedOnlyEntity,
    RuntimeSpan,
    UnresolvedObservation,
    day_bucket,
)
from app.telemetry.operation_resolver import DeclaredOperationCandidate, resolve_operation
from app.telemetry.semconv.http import HTTP_REQUEST_METHOD, HTTP_ROUTE, URL_TEMPLATE
from app.telemetry.service_resolver import (
    DeclaredServiceCandidate,
    ResolvedObservation,
    resolve_runtime_span,
)

NO_ENVIRONMENT = "no_environment"
NO_STABLE_ROUTE = "no_stable_route"


def _find_correlated_pairs(spans: list[RuntimeSpan]) -> list[tuple[RuntimeSpan, RuntimeSpan]]:
    """Pairs each SERVER span with its correlated CLIENT span (same trace_id,
    server.parent_span_id == client.span_id) WITHIN this list only. An unpaired span in this batch
    (either kind) contributes nothing - see correlate_http_call_observations's docstring."""
    clients_by_key = {(s.trace_id, s.span_id): s for s in spans if s.span_kind == "CLIENT"}
    pairs = []
    for span in spans:
        if span.span_kind != "SERVER" or span.parent_span_id is None:
            continue
        client = clients_by_key.get((span.trace_id, span.parent_span_id))
        if client is not None:
            pairs.append((client, span))
    return pairs


def _record_if_observed_only(
    entities: dict[str, ObservedOnlyEntity], resolution: ResolvedObservation, *, name: str
) -> None:
    if resolution.discovery_status == DiscoveryStatus.OBSERVED_ONLY:
        entities[resolution.service_id] = ObservedOnlyEntity(
            id=resolution.service_id, label="Service", name=name
        )


def correlate_http_call_observations(
    spans: list[RuntimeSpan],
    *,
    service_candidates: list[DeclaredServiceCandidate],
    operation_candidates: list[DeclaredOperationCandidate],
    service_aliases: dict[str, str],
) -> ObservationBatch:
    """Correlates HTTP CLIENT/SERVER span pairs into observed CALLS relationships (spec §20-23).

    Correlation is scoped to spans present in this one decoded OTLP batch only. A call whose client
    and server spans are exported in different /v1/traces POSTs produces zero observations here -
    an accepted, permanent PoC limitation (real OTel Collector batch processors flush by time/size,
    not trace completeness, so this is a genuine and not-rare gap for async/cross-service calls),
    not a bug. Building cross-batch stateful pairing (buffering spans across requests with an
    eviction policy) is exactly the "trace store"/causality graph spec §4.2 explicitly excludes.

    Environment, method, route, and timestamp are read from the SERVER span, not the client - this
    is necessary, not just a style choice: declared Operation ids are minted from the provider's own
    OpenAPI path, so sourcing the route from the client's url.template instead risks a lexical
    mismatch against the declared path string, silently breaking Fall A matching (H4.6).
    source_service_version comes from the CLIENT span (the "source"/calling side).
    """
    facts: list[ObservedFactCandidate] = []
    entities: dict[str, ObservedOnlyEntity] = {}
    unresolved: list[UnresolvedObservation] = []

    for client, server in _find_correlated_pairs(spans):
        caller = resolve_runtime_span(service_candidates, client, aliases=service_aliases)
        provider = resolve_runtime_span(service_candidates, server, aliases=service_aliases)
        _record_if_observed_only(entities, caller, name=client.service_name)
        _record_if_observed_only(entities, provider, name=server.service_name)

        if not server.environment:
            # Never guess an environment - a fabricated placeholder could quietly pollute a later
            # environment-scoped analysis (spec §14/§40's "don't invent facts" principle).
            unresolved.append(
                UnresolvedObservation(trace_id=server.trace_id, reason=NO_ENVIRONMENT)
            )
            continue

        method = server.attributes.get(HTTP_REQUEST_METHOD)
        route = server.attributes.get(HTTP_ROUTE) or server.attributes.get(URL_TEMPLATE)
        if not method or not route:
            unresolved.append(
                UnresolvedObservation(trace_id=server.trace_id, reason=NO_STABLE_ROUTE)
            )
            continue

        operation = resolve_operation(
            operation_candidates,
            provider_service_id=provider.service_id,
            method=method,
            route=route,
        )
        if operation.operation_id is None:
            unresolved.append(
                UnresolvedObservation(trace_id=server.trace_id, reason=NO_STABLE_ROUTE)
            )
            continue
        if operation.discovery_status == DiscoveryStatus.OBSERVED_ONLY:
            entities[operation.operation_id] = ObservedOnlyEntity(
                id=operation.operation_id, label="Operation", name=f"{method} {route}"
            )

        timestamp = server.end_time
        bucket_start, bucket_end = day_bucket(timestamp)
        evidence_id = ids.observed_evidence_id(
            server.environment, bucket_start, caller.service_id, "CALLS", operation.operation_id
        )
        evidence = ObservedEvidence(
            id=evidence_id,
            environment=server.environment,
            bucket_start=bucket_start,
            bucket_end=bucket_end,
            first_seen=timestamp,
            last_seen=timestamp,
            observation_count=1,
            sample_trace_ids=[server.trace_id],
            service_version=client.service_version,
        )
        facts.append(
            ObservedFactCandidate(
                subject_id=caller.service_id,
                relation_type="CALLS",
                object_id=operation.operation_id,
                environment=server.environment,
                timestamp=timestamp,
                trace_id=server.trace_id,
                source_service_version=client.service_version,
                evidence=evidence,
            )
        )

    return ObservationBatch(entities=list(entities.values()), facts=facts, unresolved=unresolved)
