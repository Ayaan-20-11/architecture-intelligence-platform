from datetime import UTC, datetime, timedelta

from app.analysis.runtime import DEFAULT_WINDOW_HOURS, default_since


def test_default_since_uses_the_default_window():
    before = datetime.now(UTC)
    since = default_since()
    after = datetime.now(UTC)

    assert before - timedelta(hours=DEFAULT_WINDOW_HOURS) <= since
    assert since <= after - timedelta(hours=DEFAULT_WINDOW_HOURS)


def test_default_since_honors_a_custom_window():
    now = datetime.now(UTC)
    since = default_since(hours=1)

    assert now - since <= timedelta(hours=1, seconds=5)
