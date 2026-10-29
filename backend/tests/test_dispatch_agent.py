import importlib
import os
from pathlib import Path

TEST_DB = Path('/tmp/routesync_pytest.db')
os.environ.setdefault('DATABASE_URL', f'sqlite:///{TEST_DB}')
os.environ.setdefault('JWT_SECRET', 'routesync-test-secret-key-with-more-than-32-bytes')

import pytest
from fastapi.testclient import TestClient
import app.agents.base as agent_base
import app.seed as seed_module
from app.auth import hash_password
from app.database import SessionLocal
from app.main import app
from app.models.models import Driver, User

client = TestClient(app)


# ---- a scripted stand-in for the Anthropic client (no network, no cost) ----
class Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def tool_call(call_id, name, **inp):
    return Block(type='tool_use', id=call_id, name=name, input=inp)


def reply(*blocks):
    return Block(content=list(blocks), stop_reason='tool_use')


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.messages = self
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.script.pop(0)


@pytest.fixture(autouse=True)
def seeded():
    importlib.reload(seed_module)  # idempotent; guards against other test modules cleaning up the DB
    db = SessionLocal()
    if not db.query(User).filter(User.email == 'driver2@routesync.com').first():
        u = User(name='Meera Iyer', email='driver2@routesync.com', role='driver', password_hash=hash_password('Driver@123'))
        db.add(u)
        db.flush()
        db.add(Driver(user_id=u.id, vehicle_type='Van', vehicle_number='MH02XY9999', status='online',
                      current_latitude=19.0, current_longitude=72.85))
        db.commit()
    db.close()


def auth(email, password):
    token = client.post('/auth/login', json={'email': email, 'password': password}).json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def admin():
    return auth('admin@routesync.com', 'Admin@123')


def new_pending_delivery():
    h = auth('customer@routesync.com', 'Customer@123')
    r = client.post('/deliveries', headers=h, json={
        'pickup_address': 'Lower Parel', 'pickup_latitude': 18.9988, 'pickup_longitude': 72.8258,
        'dropoff_address': 'Colaba', 'dropoff_latitude': 18.9067, 'dropoff_longitude': 72.8147,
        'package_description': 'Medical Supplies', 'package_weight': 12, 'priority': 'urgent'})
    assert r.status_code == 200
    return r.json()['id']


def driver_ids():
    return {d['id'] for d in client.get('/drivers', headers=admin()).json() if d['status'] == 'online'}


def test_agent_returns_valid_proposal(monkeypatch):
    delivery_id = new_pending_delivery()
    chosen = sorted(driver_ids())[-1]
    fake = FakeClient([
        reply(tool_call('t1', 'get_delivery_details'), tool_call('t2', 'list_driver_candidates')),
        reply(tool_call('t3', 'submit_proposal', driver_id=chosen, confidence='high',
                        reasoning='Urgent medical package; this driver is closest and free.')),
    ])
    monkeypatch.setattr(agent_base, 'get_client', lambda: fake)
    r = client.post(f'/agents/dispatch/{delivery_id}', headers=admin())
    assert r.status_code == 200
    body = r.json()
    assert body['proposal']['driver_id'] == chosen
    assert body['proposal']['delivery_id'] == delivery_id
    assert [t['tool'] for t in body['trace']] == ['get_delivery_details', 'list_driver_candidates', 'submit_proposal']
    # the agent is read-only: the delivery must still be pending
    detail = client.get(f'/deliveries/{delivery_id}', headers=admin()).json()
    assert detail['delivery']['status'] == 'pending'


def test_agent_self_corrects_after_invalid_driver(monkeypatch):
    delivery_id = new_pending_delivery()
    good = sorted(driver_ids())[0]
    fake = FakeClient([
        reply(tool_call('t1', 'submit_proposal', driver_id=99999, confidence='high', reasoning='made up')),
        reply(tool_call('t2', 'submit_proposal', driver_id=good, confidence='medium', reasoning='Corrected choice.')),
    ])
    monkeypatch.setattr(agent_base, 'get_client', lambda: fake)
    r = client.post(f'/agents/dispatch/{delivery_id}', headers=admin())
    assert r.status_code == 200
    assert r.json()['proposal']['driver_id'] == good
    assert r.json()['trace'][0]['ok'] is False


def test_agent_gives_up_if_it_never_submits(monkeypatch):
    delivery_id = new_pending_delivery()
    fake = FakeClient([reply(tool_call(f't{i}', 'list_driver_candidates')) for i in range(10)])
    monkeypatch.setattr(agent_base, 'get_client', lambda: fake)
    assert client.post(f'/agents/dispatch/{delivery_id}', headers=admin()).status_code == 502


def test_not_configured_returns_503(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    delivery_id = new_pending_delivery()
    r = client.post(f'/agents/dispatch/{delivery_id}', headers=admin())
    assert r.status_code == 503
    assert 'ANTHROPIC_API_KEY' in r.json()['detail']


def test_only_pending_deliveries_and_admin_only(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    assert client.post('/agents/dispatch/3', headers=admin()).status_code == 400  # in_transit in seed data
    assert client.post('/agents/dispatch/999999', headers=admin()).status_code == 404
    customer = auth('customer@routesync.com', 'Customer@123')
    assert client.post('/agents/dispatch/1', headers=customer).status_code == 403


def test_status_endpoint(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'x')
    assert client.get('/agents/status', headers=admin()).json()['configured'] is True
    monkeypatch.delenv('ANTHROPIC_API_KEY')
    assert client.get('/agents/status', headers=admin()).json()['configured'] is False
