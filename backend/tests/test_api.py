import os
from pathlib import Path

TEST_DB = Path('/tmp/routesync_pytest.db')
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ['DATABASE_URL'] = f'sqlite:///{TEST_DB}'
os.environ['JWT_SECRET'] = 'routesync-test-secret-key-with-more-than-32-bytes'

from fastapi.testclient import TestClient
import app.seed as seed_module
from app.main import app

client = TestClient(app)


def teardown_module():
    try:
        TEST_DB.unlink()
    except FileNotFoundError:
        pass


def token(email, password):
    response = client.post('/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200
    return response.json()['access_token']


def headers(t):
    return {'Authorization': f'Bearer {t}'}


def test_health():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'healthy'}


def test_auth_and_protected_routes():
    h = headers(token('admin@routesync.com', 'Admin@123'))
    assert client.get('/auth/me', headers=h).json()['role'] == 'admin'
    assert client.get('/users', headers=h).status_code == 200
    assert client.get('/drivers', headers=h).status_code == 200
    assert client.get('/deliveries', headers=h).status_code == 200
    assert client.get('/assignments', headers=h).status_code == 200


def test_dispatch_recommendation_and_route_optimization():
    h = headers(token('admin@routesync.com', 'Admin@123'))
    response = client.get('/dispatch/recommend/1', headers=h)
    assert response.status_code == 200
    assert response.json()[0]['driver']['vehicle_number'] == 'MH01AB1234'
    response = client.post('/routes/optimize', headers=h, json={'stops': [
        {'name': 'A', 'latitude': 19.1197, 'longitude': 72.8468},
        {'name': 'B', 'latitude': 19.0607, 'longitude': 72.8362},
        {'name': 'C', 'latitude': 19.2183, 'longitude': 72.9781},
    ]})
    assert response.status_code == 200
    assert len(response.json()['stops']) == 3
    assert [x['sequence'] for x in response.json()['stops']] == [1, 2, 3]


def test_delivery_lifecycle():
    h = headers(token('admin@routesync.com', 'Admin@123'))
    for status in ['assigned', 'accepted', 'pickup_started', 'picked_up', 'in_transit', 'delivered']:
        response = client.patch('/deliveries/2/status', headers=h, json={'action': status})
        assert response.status_code == 200
        assert response.json()['status'] == status


def test_role_protection():
    h = headers(token('customer@routesync.com', 'Customer@123'))
    assert client.get('/users', headers=h).status_code == 403
    assert client.get('/dispatch/recommend/1', headers=h).status_code == 403
