from pathlib import Path

import yaml
from sqlalchemy import func, select

from app.cli import main
from app.domains.quotation.infrastructure.persistence.models import ProjectModel

FIXTURE_TEXT = (Path(__file__).parent / "fixtures" / "valid_minimal.yaml").read_text(encoding="utf-8")


def _write_variant(directory: Path, filename: str, project_name: str) -> Path:
    data = yaml.safe_load(FIXTURE_TEXT)
    data["project"]["name"] = project_name
    path = directory / filename
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _projects(session) -> int:
    return session.execute(select(func.count()).select_from(ProjectModel)).scalar_one()


def test_cli_ingests_directory_of_files(db_session, tmp_path, capsys):
    _write_variant(tmp_path, "b.yaml", "Công trình B")
    _write_variant(tmp_path, "a.yaml", "Công trình A")

    code = main(["ingest", str(tmp_path)])

    assert code == 0
    assert _projects(db_session) == 2
    printed = capsys.readouterr().out
    assert printed.index("a.yaml") < printed.index("b.yaml")


def test_cli_keeps_going_after_a_bad_file_and_exits_nonzero(db_session, tmp_path, capsys):
    (tmp_path / "a-broken.yaml").write_text("project: {name: x}\n", encoding="utf-8")
    _write_variant(tmp_path, "b-good.yaml", "Công trình tốt")

    code = main(["ingest", str(tmp_path)])

    assert code == 1
    assert _projects(db_session) == 1
    assert "a-broken.yaml" in capsys.readouterr().err


def test_cli_same_file_again_is_unchanged_and_succeeds(db_session, tmp_path, capsys):
    path = _write_variant(tmp_path, "a.yaml", "Công trình A")
    assert main(["ingest", str(path)]) == 0

    assert main(["ingest", str(path)]) == 0
    assert '"status": "unchanged"' in capsys.readouterr().out
    assert _projects(db_session) == 1


def test_cli_conflicting_content_exits_nonzero_unless_replace(db_session, tmp_path, capsys):
    path = _write_variant(tmp_path, "a.yaml", "Công trình A")
    assert main(["ingest", str(path)]) == 0
    path.write_text(path.read_text(encoding="utf-8").replace("unit_price: 95000", "unit_price: 96000"), encoding="utf-8")

    assert main(["ingest", str(path)]) == 1
    assert "--replace" in capsys.readouterr().err
    assert main(["ingest", "--replace", str(path)]) == 0
    assert '"status": "replaced"' in capsys.readouterr().out
    assert _projects(db_session) == 1
