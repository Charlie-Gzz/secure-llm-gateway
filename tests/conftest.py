import os
import socket
import threading
import time

import pytest

# Offline, fast, isolated settings for every test run.
os.environ["UPSTREAM"] = "mock"
os.environ["MOCK_LATENCY_MS"] = "0"
os.environ.setdefault("OTEL_SDK_DISABLED", "true")


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("data") / "test.db"
    os.environ["DB_PATH"] = str(path)
    return path


@pytest.fixture(scope="session")
def client(db_path):
    from fastapi.testclient import TestClient

    from gateway.config import get_settings

    get_settings.cache_clear()
    from gateway.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def live_server(db_path):
    """Run the real app with uvicorn on a free port (for SDK clients that bring their own HTTP)."""
    import uvicorn

    from gateway.config import get_settings

    get_settings.cache_clear()
    from gateway.main import app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def chat(client, content: str, **extra):
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "any", "messages": [{"role": "user", "content": content}], **extra},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()
