"""Run with pytest after installing fastapi, httpx, pytest."""
from fastapi.testclient import TestClient
from app.ui import server
import pytest


@pytest.fixture
def key_configured():
    """/api/extract answers 409 until a key is configured (server._queue). Fake that state, then restore it."""
    def drain():
        while not server.commands.empty():
            server.commands.get_nowait()
    drain()
    server.update(key_configured=True, busy=False, status="Ready")
    yield
    drain()
    server.update(key_configured=False, busy=False, status="Ready")


def _loopback_base_url():
    """TestClient's default Host (testserver) is rejected by the app's loopback-only host check."""
    for host in ("127.0.0.1", "localhost"):
        base = f"http://{host}"
        try:
            if TestClient(server.app, base_url=base).get("/api/state").status_code == 200:
                return base
        except Exception:
            continue
    return "http://127.0.0.1"


def test_extract_command_is_queued_once(key_configured):
    client = TestClient(server.app, base_url=_loopback_base_url())
    token = client.get('/api/state').json()['token']
    assert client.post('/api/extract').status_code == 403
    r = client.post('/api/extract', headers={'X-KeyForMe-Token': token})
    assert r.status_code == 200
    assert client.post('/api/extract', headers={'X-KeyForMe-Token': token}).status_code == 409
    assert server.commands.get_nowait() == 'extract'
    server.update(busy=False, status='Ready')



def test_extract_is_refused_until_a_key_is_configured():
    server.update(key_configured=False, busy=False, status="Ready")
    client = TestClient(server.app, base_url=_loopback_base_url())
    token = client.get('/api/state').json()['token']
    r = client.post('/api/extract', headers={'X-KeyForMe-Token': token})
    assert r.status_code == 409 and 'key' in r.json()['detail'].lower()
    assert server.commands.empty()
    server.update(busy=False, status='Ready')
