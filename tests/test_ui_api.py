"""Run with pytest after installing fastapi, httpx, pytest."""
from fastapi.testclient import TestClient
from app.ui import server


def test_extract_command_is_queued_once():
    client = TestClient(server.app)
    token = client.get('/api/state').json()['token']
    assert client.post('/api/extract').status_code == 403
    r = client.post('/api/extract', headers={'X-KeyForMe-Token': token})
    assert r.status_code == 200
    assert client.post('/api/extract', headers={'X-KeyForMe-Token': token}).status_code == 409
    assert server.commands.get_nowait() == 'extract'
    server.update(busy=False, status='Ready')
