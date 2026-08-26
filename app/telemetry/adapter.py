from typing import Literal

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
from app.telemetry.queue_resolver import DeclaredQueueCandidate, resolve_queue
from app.telemetry.semconv.http import HTTP_REQUEST_METHOD, HTTP_ROUTE, URL_TEMPLATE
from app.telemetry.semconv.messaging import (
    MESSAGING_DESTINATION_NAME,
    MESSAGING_OPERATION_TYPE,
    MESSAGING_SYSTEM,
)
from app.telemetry.service_resolver import DeclaredServiceCandidate, resolve_runtime_span

NO_ENVIRONMENT = "no_environment"
NO_STABLE_ROUTE = "no_stable_route"
NO_DESTINATION_NAME = "no_destination_name"


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
    entities: dict[str, ObservedOnlyEntity],
    *,
    entity_id: str,
    discovery_status: DiscoveryStatus,
    label: Literal["Service", "Operation", "Queue"],
    name: str,
) -> None:
    if discovery_status == DiscoveryStatus.OBSERVED_ONLY:
        entities[entity_id] = ObservedOnlyEntity(id=entity_id, label=label, name=name)


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
        _record_if_observed_only(
            entities,
            entity_id=caller.service_id,
            discovery_status=caller.discovery_status,
            label="Service",
            name=client.service_name,
        )
        _record_if_observed_only(
            entities,
            entity_id=provider.service_id,
            discovery_status=provider.discovery_status,
            label="Service",
            name=server.service_name,
        )

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
        _record_if_observed_only(
            entities,
            entity_id=operation.operation_id,
            discovery_status=operation.discovery_status,
            label="Operation",
            name=f"{method} {route}",
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


def correlate_queue_observations(
    spans: list[RuntimeSpan],
    *,
    service_candidates: list[DeclaredServiceCandidate],
    queue_candidates: list[DeclaredQueueCandidate],
    service_aliases: dict[str, str],
    queue_aliases: dict[str, str],
) -> ObservationBatch:
    """Builds observed SENDS/RECEIVES_FROM facts from messaging spans (spec §24-26). Unlike HTTP,
    no correlation between spans is needed - SENDS/RECEIVES_FROM are independent relations, each
    derivable from a single span alone (spec §24's existing graph model already treats them this
    way).

    Classification keys exclusively off messaging.operation.type (spec §25/§26's own literal
    examples never mention span_kind, and messaging.operation.type exists in real OTel semantic
    conventions specifically because span_kind is too coarse to disambiguate "receive" from
    "process"). A span with no recognized operation.type is not a candidate observation at all and
    is silently skipped, not reported as unresolved - the same status as an INTERNAL-kind span in
    the HTTP path.
    """
    facts: list[ObservedFactCandidate] = []
    entities: dict[str, ObservedOnlyEntity] = {}
    unresolved: list[UnresolvedObservation] = []

    for span in spans:
        operation_type = (span.attributes.get(MESSAGING_OPERATION_TYPE) or "").lower()
        if operation_type == "send":
            relation_type = "SENDS"
        elif operation_type in ("receive", "process"):
            relation_type = "RECEIVES_FROM"
        else:
            continue

        destination_name = span.attributes.get(MESSAGING_DESTINATION_NAME)
        if not destination_name:
            unresolved.append(
                UnresolvedObservation(trace_id=span.trace_id, reason=NO_DESTINATION_NAME)
            )
            continue

        if not span.environment:
            unresolved.append(UnresolvedObservation(trace_id=span.trace_id, reason=NO_ENVIRONMENT))
            continue

        service = resolve_runtime_span(service_candidates, span, aliases=service_aliases)
        _record_if_observed_only(
            entities,
            entity_id=service.service_id,
            discovery_status=service.discovery_status,
            label="Service",
            name=span.service_name,
        )

        messaging_system = span.attributes.get(MESSAGING_SYSTEM)
        queue = resolve_queue(
            queue_candidates,
            messaging_system=messaging_system,
            destination_name=destination_name,
            aliases=queue_aliases,
        )
        _record_if_observed_only(
            entities,
            entity_id=queue.queue_id,
            discovery_status=queue.discovery_status,
            label="Queue",
            name=destination_name,
        )

        timestamp = span.end_time
        bucket_start, bucket_end = day_bucket(timestamp)
        evidence_id = ids.observed_evidence_id(
            span.environment, bucket_start, service.service_id, relation_type, queue.queue_id
        )
        evidence = ObservedEvidence(
            id=evidence_id,
            environment=span.environment,
            bucket_start=bucket_start,
            bucket_end=bucket_end,
            first_seen=timestamp,
            last_seen=timestamp,
            observation_count=1,
            sample_trace_ids=[span.trace_id],
            service_version=span.service_version,
        )
        facts.append(
            ObservedFactCandidate(
                subject_id=service.service_id,
                relation_type=relation_type,
                object_id=queue.queue_id,
                environment=span.environment,
                timestamp=timestamp,
                trace_id=span.trace_id,
                source_service_version=span.service_version,
                evidence=evidence,
            )
        )

    return ObservationBatch(entities=list(entities.values()), facts=facts, unresolved=unresolved)


def adapt(
    spans: list[RuntimeSpan],
    *,
    service_candidates: list[DeclaredServiceCandidate],
    operation_candidates: list[DeclaredOperationCandidate],
    queue_candidates: list[DeclaredQueueCandidate],
    service_aliases: dict[str, str],
    queue_aliases: dict[str, str],
) -> ObservationBatch:
    """Combines HTTP and queue observations from one decoded OTLP batch into a single
    ObservationBatch (spec §9's OpenTelemetryAdapter stage).

    Deliberately narrower than the `adapt(raw_bytes)` shape noted as deferred in Iteration 11C's
    plan - still takes an already-decoded list[RuntimeSpan], not raw OTLP bytes. Composing
    decode-then-adapt, and wiring any of this into POST /v1/traces, is deferred further to
    whichever iteration first needs it (11E at the earliest, once there's something to persist).
    """
    http_batch = correlate_http_call_observations(
        spans,
        service_candidates=service_candidates,
        operation_candidates=operation_candidates,
        service_aliases=service_aliases,
    )
    queue_batch = correlate_queue_observations(
        spans,
        service_candidates=service_candidates,
        queue_candidates=queue_candidates,
        service_aliases=service_aliases,
        queue_aliases=queue_aliases,
    )

    entities: dict[str, ObservedOnlyEntity] = {}
    for entity in [*http_batch.entities, *queue_batch.entities]:
        entities[entity.id] = entity

    return ObservationBatch(
        entities=list(entities.values()),
        facts=[*http_batch.facts, *queue_batch.facts],
        unresolved=[*http_batch.unresolved, *queue_batch.unresolved],
    )
