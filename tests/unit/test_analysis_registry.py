from dataclasses import dataclass
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
