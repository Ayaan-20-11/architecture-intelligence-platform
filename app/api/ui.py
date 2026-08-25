from pathlib import Path

import neo4j
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.analysis.blast_radius import blast_radius
from app.analysis.queues import consumers_of_queue, senders_of_queue
from app.api.query import QueryResponse
from app.deps import build_question_service, get_read_session

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


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
    request: Request, service_id: str, session: neo4j.Session = Depends(get_read_session)
):
    service = session.run(
        "MATCH (s:Service {id: $id}) RETURN s.id AS id, s.name AS name", id=service_id
    ).single()
    if service is None:
        raise HTTPException(status_code=404, detail=f"service not found: {service_id}")

    provides = session.run(
        "MATCH (:Service {id: $id})-[:PROVIDES]->(o:Operation) "
        "RETURN o.method AS method, o.path AS path ORDER BY o.path",
        id=service_id,
    ).data()
    calls = session.run(
        "MATCH (:Service {id: $id})-[:CALLS]->(o:Operation)<-[:PROVIDES]-(target:Service) "
        "RETURN target.name AS service_name, o.operation_id AS operation_id ORDER BY target.name",
        id=service_id,
    ).data()
    sends = session.run(
        "MATCH (:Service {id: $id})-[:SENDS]->(q:Queue) RETURN q.id AS id, q.name AS name ORDER BY q.name",
        id=service_id,
    ).data()
    receives = session.run(
        "MATCH (:Service {id: $id})-[:RECEIVES_FROM]->(q:Queue) "
        "RETURN q.id AS id, q.name AS name ORDER BY q.name",
        id=service_id,
    ).data()
    downstream = blast_radius(session, service_id, max_depth=1)

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

    messages = session.run(
        "MATCH (:Queue {id: $id})-[:CARRIES]->(m:Message) "
        "RETURN m.name AS name, m.version AS version ORDER BY m.name",
        id=queue_id,
    ).data()
    dlq = session.run(
        "MATCH (:Queue {id: $id})-[:DEAD_LETTERS_TO]->(d:Queue) RETURN d.id AS id, d.name AS name",
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
            "dlq": dlq.data() if dlq else None,
        },
    )


@router.get("/query", response_class=HTMLResponse)
def query_page(request: Request, question: str | None = None):
    result = None
    if question:
        service = build_question_service(request)
        if service is None:
            result = QueryResponse(
                question=question,
                cypher=None,
                rows=[],
                answer="Natural language query is not configured (missing OPENAI_API_KEY, or llm.enabled is false in config.yaml).",
            )
        else:
            answer_result = service.ask(question)
            result = QueryResponse(
                question=answer_result.question,
                cypher=answer_result.cypher,
                rows=answer_result.rows,
                answer=answer_result.answer,
            )
    return templates.TemplateResponse(
        request, "query.html", {"question": question, "result": result}
    )
