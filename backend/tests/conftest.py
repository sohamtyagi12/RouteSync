from pathlib import Path


def pytest_sessionfinish(session, exitstatus):
    """Delete the shared temporary SQLite DB once, after every test module has run."""
    try:
        Path('/tmp/routesync_pytest.db').unlink()
    except FileNotFoundError:
        pass
