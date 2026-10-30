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
def seeded(monkeypatch):
    monkeypatch.setenv('AGENT_PROVIDER', 'anthropic')  # existing tests use the Claude-shaped fake
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


# ------------------------------------------------------------- Gemini (free tier)
class FakeGemini:
    def __init__(self, script):
        self.script = list(script)
        self.models = self
        self.requests = []

    def generate_content(self, **kwargs):
        self.requests.append({**kwargs, 'contents': list(kwargs['contents'])})  # snapshot
        return self.script.pop(0)


def gemini_reply(*calls):
    return Block(candidates=[Block(content='model-turn')],
                 function_calls=[Block(id=None, name=n, args=a) for n, a in calls])


def test_gemini_happy_path_with_float_ids(monkeypatch):
    monkeypatch.setenv('AGENT_PROVIDER', 'gemini')
    delivery_id = new_pending_delivery()
    chosen = sorted(driver_ids())[0]
    fake = FakeGemini([
        gemini_reply(('get_delivery_details', {}), ('list_driver_candidates', {})),
        gemini_reply(('submit_proposal', {'driver_id': float(chosen), 'confidence': 'high', 'reasoning': 'Closest.'})),
    ])
    monkeypatch.setattr(agent_base, 'get_client', lambda: fake)
    r = client.post(f'/agents/dispatch/{delivery_id}', headers=admin())
    assert r.status_code == 200
    assert r.json()['proposal']['driver_id'] == chosen          # float 1.0 coerced to int
    sent_back = fake.requests[1]['contents'][-1]                 # tool results sent to Gemini
    assert [p.function_response.name for p in sent_back.parts] == ['get_delivery_details', 'list_driver_candidates']
    assert 'result' in sent_back.parts[1].function_response.response


def test_gemini_error_is_returned_to_model(monkeypatch):
    monkeypatch.setenv('AGENT_PROVIDER', 'gemini')
    delivery_id = new_pending_delivery()
    good = sorted(driver_ids())[0]
    fake = FakeGemini([
        gemini_reply(('submit_proposal', {'driver_id': 424242, 'confidence': 'high', 'reasoning': 'x'})),
        gemini_reply(('submit_proposal', {'driver_id': good, 'confidence': 'low', 'reasoning': 'fixed'})),
    ])
    monkeypatch.setattr(agent_base, 'get_client', lambda: fake)
    r = client.post(f'/agents/dispatch/{delivery_id}', headers=admin())
    assert r.status_code == 200 and r.json()['proposal']['driver_id'] == good
    assert 'error' in fake.requests[1]['contents'][-1].parts[0].function_response.response


def test_gemini_tool_declarations_are_valid(monkeypatch):
    monkeypatch.setenv('AGENT_PROVIDER', 'gemini')
    delivery_id = new_pending_delivery()
    fake = FakeGemini([gemini_reply(('submit_proposal', {'driver_id': sorted(driver_ids())[0], 'confidence': 'low', 'reasoning': 'ok'}))])
    monkeypatch.setattr(agent_base, 'get_client', lambda: fake)
    assert client.post(f'/agents/dispatch/{delivery_id}', headers=admin()).status_code == 200
    declared = {d.name: d for d in fake.requests[0]['config'].tools[0].function_declarations}
    assert declared['get_delivery_details'].parameters is None   # no-arg tools omit empty schemas
    assert declared['submit_proposal'].parameters.required == ['driver_id', 'confidence', 'reasoning']


def test_provider_auto_detection(monkeypatch):
    for var in ('AGENT_PROVIDER', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'ANTHROPIC_API_KEY', 'AGENT_MODEL'):
        monkeypatch.delenv(var, raising=False)
    assert agent_base.provider_name() is None and not agent_base.agents_configured()
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'x')
    assert agent_base.provider_name() == 'anthropic'
    monkeypatch.setenv('GEMINI_API_KEY', 'y')                     # Gemini wins when both exist
    assert agent_base.provider_name() == 'gemini'
    assert agent_base.agent_model() == agent_base.GEMINI_DEFAULT_MODEL


# ---- Delivery Intake Agent endpoint ----
def customer_headers():
    return auth('customer@routesync.com', 'Customer@123')


def driver_headers():
    return auth('driver@routesync.com', 'Driver@123')


def delivery_count():
    return len(client.get('/deliveries', headers=admin()).json())


def intake_script():
    return [reply(tool_call('i1', 'submit_draft', pickup_place='Powai', dropoff_place='Thane',
                            package_description='Documents', priority='urgent'))]


def test_intake_endpoint_returns_a_draft_for_a_customer(monkeypatch):
    fake = FakeClient(intake_script())
    monkeypatch.setattr(agent_base, 'get_client', lambda: fake)
    r = client.post('/agents/intake', headers=customer_headers(),
                    json={'text': 'Documents from Powai to Thane, urgent'})
    assert r.status_code == 200
    draft = r.json()['draft']
    assert draft['pickup_address'] == 'Powai, Mumbai'
    assert draft['dropoff_address'] == 'Thane West'
    assert draft['priority'] == 'urgent'


def test_intake_endpoint_creates_nothing(monkeypatch):
    before = delivery_count()
    fake = FakeClient(intake_script())
    monkeypatch.setattr(agent_base, 'get_client', lambda: fake)
    r = client.post('/agents/intake', headers=customer_headers(),
                    json={'text': 'Documents from Powai to Thane, urgent'})
    assert r.status_code == 200
    assert delivery_count() == before  # a draft is not a delivery


def test_intake_endpoint_is_closed_to_drivers(monkeypatch):
    fake = FakeClient(intake_script())
    monkeypatch.setattr(agent_base, 'get_client', lambda: fake)
    r = client.post('/agents/intake', headers=driver_headers(), json={'text': 'Documents from Powai to Thane'})
    assert r.status_code == 403
    assert len(fake.requests) == 0  # the AI was never called


def test_intake_endpoint_needs_a_login():
    r = client.post('/agents/intake', json={'text': 'Documents from Powai to Thane'})
    assert r.status_code in (401, 403)


@pytest.mark.parametrize('text', ['   ', 'x' * 501])
def test_intake_endpoint_rejects_empty_and_overlong_text(text):
    r = client.post('/agents/intake', headers=customer_headers(), json={'text': text})
    assert r.status_code == 400
