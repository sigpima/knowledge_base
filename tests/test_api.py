from fastapi.testclient import TestClient

from app.interfaces.http.api import app

def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


import logging


def test_startup_logs_database_initialization(caplog):
    from fastapi.testclient import TestClient
    from app.interfaces.http.api import app

    with caplog.at_level(logging.INFO):
        with TestClient(app):
            pass

    assert "Initializing database" in caplog.text


def test_run_binds_to_the_configured_host_which_defaults_to_loopback(monkeypatch):
    import uvicorn

    from app.infrastructure.config.config import Settings
    from app.interfaces.http import api

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))

    api.run(port=8123)

    assert Settings(_env_file=None).api_host == "127.0.0.1"
    assert calls == [{"host": api.settings.api_host, "port": 8123}]
