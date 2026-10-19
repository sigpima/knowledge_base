import time
from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.infrastructure.config.config import settings
from app.interfaces.http.api import app
from app.domains.quotation.infrastructure.persistence.models import ProjectModel, WorkItemModel

FIXTURE_TEXT = (Path(__file__).parent / "fixtures" / "valid_minimal.yaml").read_text(encoding="utf-8")
YAML_HEADERS = {"Content-Type": "application/x-yaml; charset=utf-8"}


def _post(text: str, **params):
    with TestClient(app) as client:
        return client.post("/ingest", content=text.encode("utf-8"), headers=YAML_HEADERS, params=params)


def _count(session, model) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def test_post_ingest_valid_returns_201_and_rows_exist(db_session):
    response = _post(FIXTURE_TEXT, source_file="hoa-sua.yaml")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"project_id", "quotation_id", "work_item_count", "has_estimation", "extra_count", "status"}
    assert body["status"] == "created"
    assert (body["work_item_count"], body["has_estimation"], body["extra_count"]) == (3, True, 1)
    assert _count(db_session, WorkItemModel) == 3
    assert db_session.get(ProjectModel, body["project_id"]).source_file == "hoa-sua.yaml"


def test_post_ingest_invalid_returns_422_with_paths(db_session):
    broken = FIXTURE_TEXT.replace("key: son-lan-can", "key: ngoai-that-tuong")

    response = _post(broken)

    assert response.status_code == 422
    assert any(e.startswith("quotation.packages[1].work_items[0].key") for e in response.json()["errors"])
    assert _count(db_session, ProjectModel) == 0


CHANGED_TEXT = FIXTURE_TEXT.replace("unit_price: 95000", "unit_price: 96000")


def test_post_same_content_again_returns_200_unchanged(db_session):
    first = _post(FIXTURE_TEXT)
    second = _post(FIXTURE_TEXT)

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["status"] == "unchanged"
    assert second.json()["project_id"] == first.json()["project_id"]
    assert _count(db_session, ProjectModel) == 1


def test_post_same_name_different_content_returns_409_with_hint(db_session):
    assert _post(FIXTURE_TEXT).status_code == 201

    response = _post(CHANGED_TEXT)

    assert response.status_code == 409
    assert "on_conflict=replace" in response.json()["detail"]
    assert _count(db_session, ProjectModel) == 1


def test_post_with_on_conflict_replace_swaps_the_project(db_session):
    first = _post(FIXTURE_TEXT)

    response = _post(CHANGED_TEXT, on_conflict="replace")

    assert response.status_code == 200
    assert response.json()["status"] == "replaced"
    assert response.json()["project_id"] != first.json()["project_id"]
    assert _count(db_session, ProjectModel) == 1


def test_post_with_unknown_on_conflict_value_returns_422(db_session):
    assert _post(FIXTURE_TEXT, on_conflict="overwrite").status_code == 422


def test_post_ingest_oversized_body_returns_413(db_session, monkeypatch):
    monkeypatch.setattr(settings, "ingest_max_body_bytes", 200)

    response = _post(FIXTURE_TEXT)

    assert response.status_code == 413
    assert _count(db_session, ProjectModel) == 0


def test_post_ingest_rejects_python_tag_with_422(db_session):
    response = _post("project: !!python/object/apply:os.system ['echo hi']\n")

    assert response.status_code == 422


def test_post_ingest_alias_bomb_is_rejected_quickly(db_session):
    laughs = "a: &a [x, x, x, x, x, x, x, x, x]\n" + "".join(
        f"{chr(98 + i)}: &{chr(98 + i)} [{', '.join(['*' + chr(97 + i)] * 9)}]\n" for i in range(8)
    )

    started = time.monotonic()
    response = _post(laughs)

    assert response.status_code == 422
    assert time.monotonic() - started < 5


def test_post_ingest_non_utf8_body_returns_422(db_session):
    with TestClient(app) as client:
        response = client.post("/ingest", content=b"\xff\xfe\x00bad", headers=YAML_HEADERS)

    assert response.status_code == 422


def test_post_ingest_rejects_non_yaml_content_type_with_415(db_session):
    with TestClient(app) as client:
        for headers in ({"Content-Type": "text/plain"}, {"Content-Type": "application/json"}, {}):
            response = client.post("/ingest", content=FIXTURE_TEXT.encode("utf-8"), headers=headers)
            assert response.status_code == 415, headers

    assert _count(db_session, ProjectModel) == 0


def test_post_ingest_accepts_the_yaml_content_types(db_session):
    for index, content_type in enumerate(("application/x-yaml", "application/yaml", "text/yaml; charset=utf-8")):
        text = FIXTURE_TEXT.replace("Biệt thự Hoa Sữa", f"Biệt thự Hoa Sữa {index}")
        with TestClient(app) as client:
            response = client.post("/ingest", content=text.encode("utf-8"), headers={"Content-Type": content_type})
        assert response.status_code == 201, content_type
