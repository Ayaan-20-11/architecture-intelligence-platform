from datetime import datetime
from typing import Literal

from app.canonical import ids
from app.provenance.model import ObservedEvidence
from app.telemetry.correlation_buffer import HttpCorrelationBuffer, PendingHttpSpan
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
from app.telemetry.service_resolver import (
    DeclaredServiceCandidate,
    resolve_runtime_span,
    resolve_service,
)

NO_ENVIRONMENT = "no_environment"
NO_STABLE_ROUTE = "no_stable_route"
NO_DESTINATION_NAME = "no_destination_name"


def _find_correlated_pairs(
    spans: list[RuntimeSpan],
) -> tuple[list[tuple[RuntimeSpan, RuntimeSpan]], list[RuntimeSpan], list[RuntimeSpan]]:
    """Pairs each SERVER span with its correlated CLIENT span (same trace_id,
    server.parent_span_id == client.span_id) WITHIN this list only, and also returns the CLIENT/
    SERVER spans that didn't pair up in this batch - candidates for cross-batch correlation via an
    HttpCorrelationBuffer (11H R2/spec §6), if the caller supplies one. A SERVER span with no
    parent_span_id can never pair with anything by construction and is silently excluded from both
    the pairs and the leftover-server list, exactly as it was silently excluded before."""
    clients_by_key = {(s.trace_id, s.span_id): s for s in spans if s.span_kind == "CLIENT"}
    matched_client_keys: set[tuple[str, str]] = set()
    pairs = []
    leftover_servers = []
    for span in spans:
        if span.span_kind != "SERVER" or span.parent_span_id is None:
            continue
        key = (span.trace_id, span.parent_span_id)
        client = clients_by_key.get(key)
        if client is not None:
            pairs.append((client, span))
            matched_client_keys.add(key)
        else:
            leftover_servers.append(span)
    leftover_clients = [
        s
        for s in spans
        if s.span_kind == "CLIENT" and (s.trace_id, s.span_id) not in matched_client_keys
    ]
    return pairs, leftover_clients, leftover_servers


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


def _build_call_fact(
    *,
    operation_candidates: list[DeclaredOperationCandidate],
    entities: dict[str, ObservedOnlyEntity],
    caller_service_id: str,
    provider_service_id: str,
    caller_service_version: str | None,
    environment: str,
    method: str,
    route: str,
    timestamp: datetime,
    trace_id: str,
) -> ObservedFactCandidate | None:
    """Shared CALLS-fact core for both in-batch and cross-batch correlated observations, once both
    sides' service identity is already resolved and environment/method/route are known to be
    present - the piece of fact-construction logic (operation resolution, evidence, the fact
    itself) that's identical regardless of how the CLIENT/SERVER pair was correlated. Returns None
    (never guessed) if the operation can't be resolved - callers report NO_STABLE_ROUTE."""
    operation = resolve_operation(
        operation_candidates, provider_service_id=provider_service_id, method=method, route=route
    )
    if operation.operation_id is None:
        return None
    _record_if_observed_only(
        entities,
        entity_id=operation.operation_id,
        discovery_status=operation.discovery_status,
        label="Operation",
        name=f"{method} {route}",
    )

    bucket_start, bucket_end = day_bucket(timestamp)
    evidence_id = ids.observed_evidence_id(
        environment, bucket_start, caller_service_id, "CALLS", operation.operation_id
    )
    evidence = ObservedEvidence(
        id=evidence_id,
        environment=environment,
        bucket_start=bucket_start,
        bucket_end=bucket_end,
        first_seen=timestamp,
        last_seen=timestamp,
        observation_count=1,
        sample_trace_ids=[trace_id],
        service_version=caller_service_version,
    )
    return ObservedFactCandidate(
        subject_id=caller_service_id,
        relation_type="CALLS",
        object_id=operation.operation_id,
        environment=environment,
        timestamp=timestamp,
        trace_id=trace_id,
        source_service_version=caller_service_version,
        evidence=evidence,
    )


def _pending_span_from_server(server: RuntimeSpan, *, method: str, route: str) -> PendingHttpSpan:
    return PendingHttpSpan(
        trace_id=server.trace_id,
        span_id=server.span_id,
        parent_span_id=server.parent_span_id,
        span_kind="SERVER",
        service_name=server.service_name,
        service_namespace=server.service_namespace,
        service_version=server.service_version,
        environment=server.environment,
        method=method,
        route=route,
        timestamp=server.end_time,
    )


def _pending_span_from_client(client: RuntimeSpan) -> PendingHttpSpan:
    return PendingHttpSpan(
        trace_id=client.trace_id,
        span_id=client.span_id,
        parent_span_id=client.parent_span_id,
        span_kind="CLIENT",
        service_name=client.service_name,
        service_namespace=client.service_namespace,
        service_version=client.service_version,
        environment=client.environment,
        timestamp=client.end_time,
    )


def correlate_http_call_observations(
    spans: list[RuntimeSpan],
    *,
    service_candidates: list[DeclaredServiceCandidate],
    operation_candidates: list[DeclaredOperationCandidate],
    service_aliases: dict[str, str],
    correlation_buffer: HttpCorrelationBuffer | None = None,
) -> ObservationBatch:
    """Correlates HTTP CLIENT/SERVER span pairs into observed CALLS relationships (spec §20-23).

    Pairing happens in two phases. First, within this one decoded OTLP batch
    (_find_correlated_pairs). Second, for whichever CLIENT/SERVER spans didn't pair up in this
    batch, against a caller-supplied HttpCorrelationBuffer (11H R2/spec §6) - a bounded, TTL-based,
    in-memory store of spans still awaiting their counterpart from a *different* /v1/traces POST.
    This supersedes H4's original single-batch-only limitation: real OTel Collector batch
    processors flush by time/size, not trace completeness, so a call's two sides frequently arrive
    in separate batches - the buffer (never a Neo4j Span store, never unbounded, spec
    §6.3/§13/§14) closes that gap while still never becoming the "trace store"/causality graph
    this platform deliberately stays out of. Passing correlation_buffer=None (the default) skips
    the second phase entirely, preserving exactly the original single-batch-only behavior -
    existing callers/tests are unaffected.

    Environment, method, route, and timestamp are always read from the SERVER span, not the
    client - this is necessary, not just a style choice: declared Operation ids are minted from
    the provider's own OpenAPI path, so sourcing the route from the client's url.template instead
    risks a lexical mismatch against the declared path string, silently breaking Fall A matching
    (H4.6). This holds identically whether the SERVER span was seen in-batch or arrived from the
    correlation buffer. source_service_version comes from the CLIENT span (the "source"/calling
    side) in both phases too.
    """
    facts: list[ObservedFactCandidate] = []
    entities: dict[str, ObservedOnlyEntity] = {}
    unresolved: list[UnresolvedObservation] = []

    pairs, leftover_clients, leftover_servers = _find_correlated_pairs(spans)

    for client, server in pairs:
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

        fact = _build_call_fact(
            operation_candidates=operation_candidates,
            entities=entities,
            caller_service_id=caller.service_id,
            provider_service_id=provider.service_id,
            caller_service_version=client.service_version,
            environment=server.environment,
            method=method,
            route=route,
            timestamp=server.end_time,
            trace_id=server.trace_id,
        )
        if fact is None:
            unresolved.append(
                UnresolvedObservation(trace_id=server.trace_id, reason=NO_STABLE_ROUTE)
            )
            continue
        facts.append(fact)

    if correlation_buffer is not None:
        for server in leftover_servers:
            if not server.environment:
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

            provider = resolve_runtime_span(service_candidates, server, aliases=service_aliases)
            _record_if_observed_only(
                entities,
                entity_id=provider.service_id,
                discovery_status=provider.discovery_status,
                label="Service",
                name=server.service_name,
            )

            matched_client = correlation_buffer.offer_server(
                _pending_span_from_server(server, method=method, route=route)
            )
            if matched_client is None:
                continue

            caller = resolve_service(
                service_candidates,
                service_name=matched_client.service_name,
                service_namespace=matched_client.service_namespace,
                aliases=service_aliases,
            )
            _record_if_observed_only(
                entities,
                entity_id=caller.service_id,
                discovery_status=caller.discovery_status,
                label="Service",
                name=matched_client.service_name,
            )

            fact = _build_call_fact(
                operation_candidates=operation_candidates,
                entities=entities,
                caller_service_id=caller.service_id,
                provider_service_id=provider.service_id,
                caller_service_version=matched_client.service_version,
                environment=server.environment,
                method=method,
                route=route,
                timestamp=server.end_time,
                trace_id=server.trace_id,
            )
            if fact is not None:
                facts.append(fact)

        for client in leftover_clients:
            caller = resolve_runtime_span(service_candidates, client, aliases=service_aliases)
            _record_if_observed_only(
                entities,
                entity_id=caller.service_id,
                discovery_status=caller.discovery_status,
                label="Service",
                name=client.service_name,
            )

            matched_server = correlation_buffer.offer_client(_pending_span_from_client(client))
            if matched_server is None:
                continue
            # Every SERVER PendingHttpSpan the buffer ever stores was validated (environment,
            # method, route all present) before being offered - see the leftover_servers loop
            # above, the only place offer_server() is ever called.
            assert matched_server.environment and matched_server.method and matched_server.route

            provider = resolve_service(
                service_candidates,
                service_name=matched_server.service_name,
                service_namespace=matched_server.service_namespace,
                aliases=service_aliases,
            )
            _record_if_observed_only(
                entities,
                entity_id=provider.service_id,
                discovery_status=provider.discovery_status,
                label="Service",
                name=matched_server.service_name,
            )

            fact = _build_call_fact(
                operation_candidates=operation_candidates,
                entities=entities,
                caller_service_id=caller.service_id,
                provider_service_id=provider.service_id,
                caller_service_version=client.service_version,
                environment=matched_server.environment,
                method=matched_server.method,
                route=matched_server.route,
                timestamp=matched_server.timestamp,
                trace_id=matched_server.trace_id,
            )
            if fact is not None:
                facts.append(fact)

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
    correlation_buffer: HttpCorrelationBuffer | None = None,
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
        correlation_buffer=correlation_buffer,
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
