from pathlib import Path

import neo4j
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.analysis.blast_radius import blast_radius
from app.analysis.queues import consumers_of_queue, senders_of_queue
from app.analysis.runtime import default_since, service_runtime_profile
from app.answer_router import LLMNotConfiguredError, answer_question
from app.api.query import QueryResponse
from app.deps import build_question_service, get_read_session, get_settings
from app.settings import Settings

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

_EVIDENCE_BY_IDS_QUERY = (
    "UNWIND $ids AS eid "
    "MATCH (e:Evidence {id: eid}) "
    "RETURN e.id AS id, e.source_type AS source_type, e.source_file AS source_file, "
    "e.source_revision AS source_revision, e.evidence_type AS evidence_type, "
    "e.environment AS environment, e.first_seen AS first_seen, e.last_seen AS last_seen, "
    "e.observation_count AS observation_count"
)


def _humanize_window_hours(hours: int) -> str:
    if hours % 24 == 0:
        days = hours // 24
        return "1 day" if days == 1 else f"{days} days"
    return f"{hours}h"


def _attach_evidence(session: neo4j.Session, rows: list[dict]) -> list[dict]:
    """Resolves each row's evidence_ids into full Evidence records in one batch query (spec §4.11)."""
    all_ids = {eid for row in rows for eid in row.get("evidence_ids") or []}
    evidence_by_id = (
        {
            record["id"]: record.data()
            for record in session.run(_EVIDENCE_BY_IDS_QUERY, ids=list(all_ids))
        }
        if all_ids
        else {}
    )
    for row in rows:
        row["evidence"] = [
            evidence_by_id[eid] for eid in row.get("evidence_ids") or [] if eid in evidence_by_id
        ]
    return rows


@router.get("/", response_class=HTMLResponse)
def index(request: Request, session: neo4j.Session = Depends(get_read_session)):
    services = session.run(
        "MATCH (s:Service) RETURN s.id AS id, s.name AS name ORDER BY s.name"
    ).data()
    queues = session.run("MATCH (q:Queue) RETURN q.id AS id, q.name AS name ORDER BY q.name").data()
    return templates.TemplateResponse(
        request, "index.html", {"services": services, "queues": queues}
    )


@router.get("/services/{service_id}", response_class=HTMLResponse)
def service_explorer(
    request: Request,
    service_id: str,
    environment: str | None = None,
    session: neo4j.Session = Depends(get_read_session),
    settings: Settings = Depends(get_settings),
):
    service = session.run(
        "MATCH (s:Service {id: $id}) RETURN s.id AS id, s.name AS name", id=service_id
    ).single()
    if service is None:
        raise HTTPException(status_code=404, detail=f"service not found: {service_id}")

    provides = _attach_evidence(
        session,
        session.run(
            "MATCH (:Service {id: $id})-[r:PROVIDES]->(o:Operation) "
            "RETURN o.method AS method, o.path AS path, r.evidence_ids AS evidence_ids "
            "ORDER BY o.path",
            id=service_id,
        ).data(),
    )
    calls = _attach_evidence(
        session,
        session.run(
            "MATCH (:Service {id: $id})-[r:CALLS]->(o:Operation)<-[:PROVIDES]-(target:Service) "
            "RETURN target.name AS service_name, o.operation_id AS operation_id, "
            "r.evidence_ids AS evidence_ids ORDER BY target.name",
            id=service_id,
        ).data(),
    )
    sends = _attach_evidence(
        session,
        session.run(
            "MATCH (:Service {id: $id})-[r:SENDS]->(q:Queue) "
            "RETURN q.id AS id, q.name AS name, r.evidence_ids AS evidence_ids ORDER BY q.name",
            id=service_id,
        ).data(),
    )
    receives = _attach_evidence(
        session,
        session.run(
            "MATCH (:Service {id: $id})-[r:RECEIVES_FROM]->(q:Queue) "
            "RETURN q.id AS id, q.name AS name, r.evidence_ids AS evidence_ids ORDER BY q.name",
            id=service_id,
        ).data(),
    )
    downstream = blast_radius(session, service_id, max_depth=1)

    env = environment or settings.config.runtime_analysis.default_environment
    since = default_since(settings.config.runtime_analysis.default_window_hours)
    observed = service_runtime_profile(session, service_id=service_id, environment=env, since=since)

    return templates.TemplateResponse(
        request,
        "service.html",
        {
            "service": service.data(),
            "provides": provides,
            "calls": calls,
            "sends": sends,
            "receives": receives,
            "downstream": downstream,
            "observed": observed,
            "observed_window_label": _humanize_window_hours(
                settings.config.runtime_analysis.default_window_hours
            ),
        },
    )


@router.get("/queues/{queue_id}", response_class=HTMLResponse)
def queue_explorer(
    request: Request, queue_id: str, session: neo4j.Session = Depends(get_read_session)
):
    queue = session.run(
        "MATCH (q:Queue {id: $id}) RETURN q.id AS id, q.name AS name, q.protocol AS protocol",
        id=queue_id,
    ).single()
    if queue is None:
        raise HTTPException(status_code=404, detail=f"queue not found: {queue_id}")

    messages = _attach_evidence(
        session,
        session.run(
            "MATCH (:Queue {id: $id})-[r:CARRIES]->(m:Message) "
            "RETURN m.name AS name, m.version AS version, r.evidence_ids AS evidence_ids "
            "ORDER BY m.name",
            id=queue_id,
        ).data(),
    )
    dlq = session.run(
        "MATCH (:Queue {id: $id})-[r:DEAD_LETTERS_TO]->(d:Queue) "
        "RETURN d.id AS id, d.name AS name, r.evidence_ids AS evidence_ids",
        id=queue_id,
    ).single()

    return templates.TemplateResponse(
        request,
        "queue.html",
        {
            "queue": queue.data(),
            "senders": senders_of_queue(session, queue_id),
            "consumers": consumers_of_queue(session, queue_id),
            "messages": messages,
            "dlq": _attach_evidence(session, [dlq.data()])[0] if dlq else None,
        },
    )


@router.get("/query", response_class=HTMLResponse)
def query_page(
    request: Request,
    question: str | None = None,
    session: neo4j.Session = Depends(get_read_session),
):
    result = None
    if question:
        settings = get_settings(request)
        question_service = build_question_service(request)
        try:
            routed = answer_question(
                session=session,
                question=question,
                deterministic_threshold=settings.config.intent_router.deterministic_threshold,
                question_service=question_service,
                default_window_hours=settings.config.runtime_analysis.default_window_hours,
                default_environment=settings.config.runtime_analysis.default_environment,
            )
            result = QueryResponse(
                question=routed.question,
                cypher=routed.cypher,
                rows=routed.rows,
                answer=routed.answer,
                execution_mode=routed.execution_mode,
                intent=routed.intent,
            )
        except LLMNotConfiguredError:
            result = QueryResponse(
                question=question,
                cypher=None,
                rows=[],
                answer="Natural language query is not configured (missing OPENAI_API_KEY, or llm.enabled is false in config.yaml).",
            )
    return templates.TemplateResponse(
        request, "query.html", {"question": question, "result": result}
    )
