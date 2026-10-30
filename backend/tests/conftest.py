from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _agent_rate_limits(monkeypatch):
    """Keep the AI rate limiter out of the way of other tests (test_ratelimit.py sets its own)."""
    monkeypatch.setenv('AGENT_RATE_LIMIT', '10000')
    monkeypatch.setenv('AGENT_GLOBAL_LIMIT', '100000')
    from app.agents import ratelimit
    ratelimit.reset()


def pytest_sessionfinish(session, exitstatus):
    """Delete the shared temporary SQLite DB once, after every test module has run."""
    try:
        Path('/tmp/routesync_pytest.db').unlink()
    except FileNotFoundError:
        pass
