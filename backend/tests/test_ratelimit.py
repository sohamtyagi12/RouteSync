import importlib
import os
from pathlib import Path
from types import SimpleNamespace

TEST_DB = Path('/tmp/routesync_pytest.db')
os.environ.setdefault('DATABASE_URL', f'sqlite:///{TEST_DB}')
os.environ.setdefault('JWT_SECRET', 'routesync-test-secret-key-with-more-than-32-bytes')

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
import app.seed as seed_module
from app.agents import ratelimit
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    importlib.reload(seed_module)  # idempotent; keeps the shared test DB seeded
    for var in ('GEMINI_API_KEY', 'GOOGLE_API_KEY', 'ANTHROPIC_API_KEY', 'AGENT_PROVIDER'):
        monkeypatch.delenv(var, raising=False)  # no key: calls end in 503, which is fine here


def login(email, password):
    token = client.post('/auth/login', json={'email': email, 'password': password}).json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def admin():
    return login('admin@routesync.com', 'Admin@123')


def customer():
    return login('customer@routesync.com', 'Customer@123')


def intake(headers):
    return client.post('/agents/intake', headers=headers, json={'text': 'documents from Powai to Thane'})


def test_user_is_blocked_after_the_limit(monkeypatch):
    monkeypatch.setenv('AGENT_RATE_LIMIT', '2')
    h = admin()
    assert intake(h).status_code != 429
    assert intake(h).status_code != 429
    blocked = intake(h)
    assert blocked.status_code == 429
    assert 'Try again' in blocked.json()['detail']
    assert int(blocked.headers['retry-after']) > 0


def test_limit_is_per_user(monkeypatch):
    monkeypatch.setenv('AGENT_RATE_LIMIT', '1')
    assert intake(admin()).status_code != 429
    assert intake(admin()).status_code == 429
    assert intake(customer()).status_code != 429   # a different user still has quota


def test_global_daily_limit(monkeypatch):
    monkeypatch.setenv('AGENT_GLOBAL_LIMIT', '2')
    assert intake(admin()).status_code != 429
    assert intake(customer()).status_code != 429
    blocked = intake(admin())
    assert blocked.status_code == 429
    assert 'site' in blocked.json()['detail']


def test_status_endpoint_is_not_limited(monkeypatch):
    monkeypatch.setenv('AGENT_RATE_LIMIT', '1')
    h = admin()
    assert all(client.get('/agents/status', headers=h).status_code == 200 for _ in range(5))


def test_forbidden_requests_do_not_use_up_quota(monkeypatch):
    monkeypatch.setenv('AGENT_RATE_LIMIT', '1')
    h = customer()
    for _ in range(3):
        assert client.post('/agents/dispatch/1', headers=h).status_code == 403   # customers can't dispatch
    assert intake(h).status_code != 429


def test_window_expires(monkeypatch):
    monkeypatch.setenv('AGENT_RATE_LIMIT', '1')
    monkeypatch.setenv('AGENT_RATE_WINDOW', '60')
    clock = {'now': 1000.0}
    monkeypatch.setattr(ratelimit.time, 'monotonic', lambda: clock['now'])
    user = SimpleNamespace(id=42)
    ratelimit.check_agent_rate_limit(user)
    with pytest.raises(HTTPException) as err:
        ratelimit.check_agent_rate_limit(user)
    assert err.value.status_code == 429
    clock['now'] += 61
    ratelimit.check_agent_rate_limit(user)   # window passed, allowed again
