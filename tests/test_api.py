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
