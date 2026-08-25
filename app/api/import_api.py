import logging
import time
import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from app.canonical.model import ArchitectureModel
from app.deps import get_driver, get_settings
from app.graph.importer import import_all_sources, import_service
from app.graph.repository import open_session
from app.graph.schema import ensure_schema
from app.ingestion.pipeline import merge_models, parse_sources
from app.settings import Settings
from app.validation.canonical_validation import validate_canonical_model

router = APIRouter(prefix="/api/import", tags=["import"])
logger = logging.getLogger("architecture_intelligence.import")


def _log_import(
    import_id: str, service_id: str, model: ArchitectureModel, duration_ms: int
) -> None:
    source_files = ",".join(sorted({p.source_file for p in model.provenance}))
    logger.info(
        "Imported import_id=%s service=%s source_file=%s operations=%d queues=%d messages=%d "
        "relations=%d duration_ms=%d",
        import_id,
        service_id,
        source_files,
        len(model.operations),
        len(model.queues),
        len(model.messages),
        len(model.relations),
        duration_ms,
    )


@router.post("")
def import_all(settings: Settings = Depends(get_settings), driver=Depends(get_driver)) -> dict:
    """POST /api/import - imports all configured sources (spec §14)."""
    import_id = uuid.uuid4().hex
    combined_stats = {}
    for directory in settings.config.sources.directories:
        start = time.perf_counter()
        by_service = parse_sources(directory)
        stats = import_all_sources(driver, database=settings.config.graph.database, root=directory)
        duration_ms = int((time.perf_counter() - start) * 1000)
        for service_id, model in by_service.items():
            _log_import(import_id, service_id, model, duration_ms)
        combined_stats.update(stats)
    return {
        "import_id": import_id,
        "services": {sid: asdict(s) for sid, s in combined_stats.items()},
    }


@router.post("/service/{service_id}")
def import_one_service(
    service_id: str, settings: Settings = Depends(get_settings), driver=Depends(get_driver)
) -> dict:
    """POST /api/import/service/{serviceId} reimports one service; service_id is the source-layer slug (e.g. "order-service"), not the graph's "service:..." id (spec §14)."""
    import_id = uuid.uuid4().hex
    by_service: dict[str, ArchitectureModel] = {}
    for directory in settings.config.sources.directories:
        by_service.update(parse_sources(directory))

    if service_id not in by_service:
        raise HTTPException(status_code=404, detail=f"no sources found for service: {service_id}")

    validate_canonical_model(merge_models(list(by_service.values())))

    start = time.perf_counter()
    with open_session(driver, database=settings.config.graph.database) as session:
        ensure_schema(session)
        stats = import_service(session, service_id, by_service[service_id])
    duration_ms = int((time.perf_counter() - start) * 1000)

    _log_import(import_id, service_id, by_service[service_id], duration_ms)
    return {"import_id": import_id, "service": asdict(stats)}
