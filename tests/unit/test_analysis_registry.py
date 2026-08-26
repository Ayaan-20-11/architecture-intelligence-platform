from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.analysis.registry import INTENT_HANDLERS, execute
from app.intent.model import ArchitectureIntent


def test_all_non_unknown_intents_have_a_handler():
    non_unknown = {i for i in ArchitectureIntent if i is not ArchitectureIntent.UNKNOWN}
    assert set(INTENT_HANDLERS.keys()) == non_unknown


def test_execute_converts_dataclass_rows_to_dicts(monkeypatch):
    @dataclass(frozen=True)
    class FakeRow:
        id: str
        name: str

    fake_session = MagicMock()
    monkeypatch.setitem(
        INTENT_HANDLERS,
        ArchitectureIntent.QUEUE_SENDERS,
        lambda session, params: [FakeRow(id="queue:x", name="x")],
    )

    rows = execute(fake_session, ArchitectureIntent.QUEUE_SENDERS, {"queue_id": "queue:x"})

    assert rows == [{"id": "queue:x", "name": "x"}]


def test_execute_merges_since_and_environment_into_params_when_provided(monkeypatch):
    """O1-O5 handlers read p["since"]/p["environment"] - execute() is what injects them, never
    classify()/entity_resolver.py (spec §51 Decision 2)."""
    seen_params = {}
    fake_session = MagicMock()
    monkeypatch.setitem(
        INTENT_HANDLERS,
        ArchitectureIntent.OBSERVED_RELATIONS,
        lambda session, params: seen_params.update(params) or [],
    )
    since = datetime(2026, 8, 26, tzinfo=UTC)

    execute(
        fake_session,
        ArchitectureIntent.OBSERVED_RELATIONS,
        {},
        since=since,
        environment="production",
    )

    assert seen_params == {"since": since, "environment": "production"}


def test_execute_without_since_or_environment_behaves_as_before(monkeypatch):
    @dataclass(frozen=True)
    class FakeRow:
        id: str

    fake_session = MagicMock()
    monkeypatch.setitem(
        INTENT_HANDLERS,
        ArchitectureIntent.QUEUE_SENDERS,
        lambda session, params: (
            [FakeRow(id="queue:x")] if params == {"queue_id": "queue:x"} else []
        ),
    )

    rows = execute(fake_session, ArchitectureIntent.QUEUE_SENDERS, {"queue_id": "queue:x"})

    assert rows == [{"id": "queue:x"}]
