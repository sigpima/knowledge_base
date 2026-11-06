import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from sqlalchemy import func, select

from app.cli import main
from app.domains.policy.application.services.chunker import PolicyChunk
from app.domains.policy.application.services.corpus import PolicyDocument, PolicyFrontMatter
from app.domains.quotation.infrastructure.persistence.models import ProjectModel

FIXTURE_TEXT = (Path(__file__).parent / "fixtures" / "valid_minimal.yaml").read_text(encoding="utf-8")


def _write_variant(directory: Path, filename: str, project_name: str) -> Path:
    data = yaml.safe_load(FIXTURE_TEXT)
    data["project"]["name"] = project_name
    path = directory / filename
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _doc(slug: str) -> PolicyDocument:
    return PolicyDocument(
        front=PolicyFrontMatter(slug=slug, title="Cũ", doc_type="technical"), body="cũ", source_name=f"{slug}.md",
        content_hash="cu",
    )


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


# ---- ingest-policies ------------------------------------------------------------------------------------------


def _policy_text(slug: str, title: str = "Tài liệu thử", body: str = "## Mục một\n\nNội dung của mục một.\n") -> str:
    return f"---\nslug: {slug}\ntitle: {title}\ndoc_type: technical\n---\n# {title}\n\n{body}"


def _write_policy(directory: Path, filename: str, slug: str, **kwargs) -> Path:
    path = directory / filename
    path.write_text(_policy_text(slug, **kwargs), encoding="utf-8")
    return path


def _seed_old(env, slug: str) -> None:
    """Đặt sẵn một tài liệu cũ vào store mà không đụng tới `env.embedder.calls`."""
    from tests.policy_fakes import HashingEmbedder

    vector = HashingEmbedder._vector("cũ")
    env.store.replace_document(_doc(slug), env.embedder.model, [PolicyChunk(index=0, section_path="T", text="cũ")], [vector])


@pytest.fixture
def policy_env(monkeypatch, policy_store):
    """Tiêm embedder giả và store Milvus Lite vào đường dẫn lazy của lệnh ingest-policies."""
    from app.domains.policy.infrastructure.embedding import gemini
    from app.domains.policy.infrastructure.vectorstore import milvus_store
    from app.infrastructure.config.config import settings
    from tests.policy_fakes import HashingEmbedder

    embedder = HashingEmbedder()
    monkeypatch.setattr(settings, "gemini_api_key", "khoa-gia-lap")
    monkeypatch.setattr(gemini, "build_embedder", lambda api_key, model, base_url="": embedder)
    monkeypatch.setattr(milvus_store, "build_milvus_store", lambda uri, token, collection, read_only=False: policy_store)
    return SimpleNamespace(embedder=embedder, store=policy_store)


def test_ingest_policies_ingests_directory_and_prunes(policy_env, tmp_path, capsys):
    _seed_old(policy_env, "cu-het-han")
    _write_policy(tmp_path, "b.md", "tai-lieu-b")
    _write_policy(tmp_path, "a.md", "tai-lieu-a")

    code = main(["ingest-policies", str(tmp_path), "--prune"])

    assert code == 0
    out = capsys.readouterr().out
    assert out.index("tai-lieu-a:") < out.index("tai-lieu-b:")
    assert '"status": "created"' in out
    assert "cu-het-han" in out
    assert policy_env.store.get_document_meta("tai-lieu-a") is not None
    assert policy_env.store.get_document_meta("cu-het-han") is None


def test_ingest_policies_again_is_unchanged_and_without_prune_keeps_extras(policy_env, tmp_path, capsys):
    _seed_old(policy_env, "tai-lieu-thua")
    _write_policy(tmp_path, "a.md", "tai-lieu-a")
    assert main(["ingest-policies", str(tmp_path)]) == 0
    calls = len(policy_env.embedder.calls)
    capsys.readouterr()

    assert main(["ingest-policies", str(tmp_path)]) == 0

    assert '"status": "unchanged"' in capsys.readouterr().out
    assert len(policy_env.embedder.calls) == calls
    assert policy_env.store.get_document_meta("tai-lieu-thua") is not None  # không có --prune thì tài liệu thừa còn nguyên


def test_ingest_policies_bad_file_exits_1_ingests_good_and_skips_prune(policy_env, tmp_path, capsys):
    _seed_old(policy_env, "khong-xoa")
    (tmp_path / "a-hong.md").write_text("không có front matter\n", encoding="utf-8")
    _write_policy(tmp_path, "b-tot.md", "tai-lieu-tot")

    code = main(["ingest-policies", str(tmp_path), "--prune"])

    assert code == 1
    captured = capsys.readouterr()
    assert "a-hong.md" in captured.err
    assert "tai-lieu-tot" in captured.out
    assert policy_env.store.get_document_meta("tai-lieu-tot") is not None
    assert policy_env.store.get_document_meta("khong-xoa") is not None


def test_ingest_policies_duplicate_slug_first_wins_later_skipped(policy_env, tmp_path, capsys):
    _seed_old(policy_env, "khong-xoa")
    _write_policy(tmp_path, "a.md", "trung-slug", title="Bản A")
    _write_policy(tmp_path, "b.md", "trung-slug", title="Bản B")
    _write_policy(tmp_path, "c.md", "khac-slug")

    code = main(["ingest-policies", str(tmp_path), "--prune"])

    assert code == 1
    captured = capsys.readouterr()
    assert "b.md" in captured.err and "trung-slug" in captured.err
    assert "khac-slug" in captured.out
    assert policy_env.store.search(
        policy_env.embedder.embed_query("Bản A"), policy_env.embedder.model, 10, None
    )[0].title == "Bản A"
    assert policy_env.store.get_document_meta("khong-xoa") is not None  # có file lỗi (trùng slug) nên --prune không chạy


def test_ingest_policies_missing_path_exits_2_without_touching_store(policy_env, tmp_path, capsys):
    _seed_old(policy_env, "con-lai")

    code = main(["ingest-policies", str(tmp_path / "go-nham"), "--prune"])

    assert code == 2
    assert "go-nham" in capsys.readouterr().err
    assert policy_env.embedder.calls == []
    assert policy_env.store.get_document_meta("con-lai") is not None


def test_ingest_policies_directory_without_markdown_exits_2(policy_env, tmp_path, capsys):
    (tmp_path / "ghi-chu.txt").write_text("không phải markdown", encoding="utf-8")

    code = main(["ingest-policies", str(tmp_path), "--prune"])

    assert code == 2
    assert "*.md" in capsys.readouterr().err
    assert policy_env.embedder.calls == []


def test_ingest_policies_missing_api_key_exits_2_and_writes_nothing(monkeypatch, policy_store, tmp_path, capsys):
    from app.domains.policy.infrastructure.vectorstore import milvus_store
    from app.infrastructure.config.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(milvus_store, "build_milvus_store", lambda *args, **kwargs: policy_store)
    _write_policy(tmp_path, "a.md", "tai-lieu-a")

    code = main(["ingest-policies", str(tmp_path)])

    assert code == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err
    assert policy_store.get_document_meta("tai-lieu-a") is None


def test_ingest_policies_milvus_unreachable_exits_2_without_leaking_uri(monkeypatch, policy_env, tmp_path, capsys):
    from app.domains.policy.infrastructure.vectorstore import milvus_store
    from app.domains.policy.infrastructure.vectorstore.base import PolicyStoreUnavailableError
    from app.infrastructure.config.config import settings

    class Unreachable:
        def ensure_collection(self):
            raise PolicyStoreUnavailableError("không kết nối được kho vector Milvus")

    monkeypatch.setattr(settings, "milvus_uri", "http://bi-mat.example:19530")
    monkeypatch.setattr(milvus_store, "build_milvus_store", lambda *args, **kwargs: Unreachable())
    _write_policy(tmp_path, "a.md", "tai-lieu-a")

    code = main(["ingest-policies", str(tmp_path)])

    assert code == 2
    err = capsys.readouterr().err
    assert "Milvus" in err and "bi-mat.example" not in err
    assert policy_env.embedder.calls == []


def test_ingest_policies_embedding_failure_on_one_file_keeps_going(monkeypatch, policy_env, tmp_path, capsys):
    from app.domains.policy.infrastructure.embedding.base import EmbeddingError

    real = policy_env.embedder.embed_documents

    def flaky(texts):
        if any("hỏng embedding" in text for text in texts):
            raise EmbeddingError("hết hạn mức")
        return real(texts)

    monkeypatch.setattr(policy_env.embedder, "embed_documents", flaky)
    _seed_old(policy_env, "khong-xoa")
    _write_policy(tmp_path, "a.md", "tai-lieu-a", body="## Mục\n\nhỏng embedding\n")
    _write_policy(tmp_path, "b.md", "tai-lieu-b")

    code = main(["ingest-policies", str(tmp_path), "--prune"])

    assert code == 1
    captured = capsys.readouterr()
    assert "a.md" in captured.err and "hết hạn mức" in captured.err
    assert policy_env.store.get_document_meta("tai-lieu-a") is None
    assert policy_env.store.get_document_meta("tai-lieu-b") is not None
    assert policy_env.store.get_document_meta("khong-xoa") is not None  # nạp lỗi một file nên --prune không chạy


def _forbid_prune(monkeypatch, store) -> list[set[str]]:
    """Thay `delete_other_than` bằng bản ghi lại lời gọi (và không xoá gì), để khẳng định --prune có chạy hay không."""
    calls: list[set[str]] = []
    monkeypatch.setattr(store, "delete_other_than", lambda keep: calls.append(set(keep)) or [])
    return calls


def test_ingest_policies_all_files_bad_with_prune_leaves_the_store_untouched(policy_env, tmp_path, capsys, monkeypatch):
    _seed_old(policy_env, "khong-xoa")
    prune_calls = _forbid_prune(monkeypatch, policy_env.store)
    (tmp_path / "a-hong.md").write_text("không có front matter\n", encoding="utf-8")
    (tmp_path / "b-hong.md").write_text("---\nslug: Sai Slug\n---\nthân\n", encoding="utf-8")

    code = main(["ingest-policies", str(tmp_path), "--prune"])

    assert code == 1
    err = capsys.readouterr().err
    assert "a-hong.md" in err and "b-hong.md" in err
    assert prune_calls == []
    assert policy_env.embedder.calls == []
    assert policy_env.store.get_document_meta("khong-xoa") is not None


def test_ingest_policies_prune_failure_exits_1_with_a_vietnamese_message_and_no_secrets(policy_env, tmp_path, capsys, monkeypatch):
    from app.domains.policy.infrastructure.vectorstore.base import PolicyStoreError

    def failing_prune(keep):
        raise PolicyStoreError("kho vector Milvus báo lỗi khi xoá tài liệu cũ")

    monkeypatch.setattr(policy_env.store, "delete_other_than", failing_prune)
    _write_policy(tmp_path, "a.md", "tai-lieu-a")

    code = main(["ingest-policies", str(tmp_path), "--prune"])

    assert code == 1
    captured = capsys.readouterr()
    assert "Lỗi khi xoá tài liệu cũ" in captured.err
    assert "Traceback" not in captured.err
    assert "tai-lieu-a" in captured.out  # tài liệu tốt vẫn được nạp trước khi prune
    assert policy_env.store.get_document_meta("tai-lieu-a") is not None
    assert "khoa-gia-lap" not in captured.err and "khoa-gia-lap" not in captured.out


def test_ingest_policies_prune_is_not_attempted_when_a_file_is_bad_even_if_prune_would_fail(policy_env, tmp_path, capsys, monkeypatch):
    from app.domains.policy.infrastructure.vectorstore.base import PolicyStoreError

    def failing_prune(keep):
        raise PolicyStoreError("prune không được gọi")

    monkeypatch.setattr(policy_env.store, "delete_other_than", failing_prune)
    (tmp_path / "a-hong.md").write_text("không có front matter\n", encoding="utf-8")
    _write_policy(tmp_path, "b.md", "tai-lieu-b")

    code = main(["ingest-policies", str(tmp_path), "--prune"])

    assert code == 1
    err = capsys.readouterr().err
    assert "--prune bị bỏ qua" in err
    assert "prune không được gọi" not in err


def test_ingest_policies_replace_document_failure_exits_1_keeps_going_and_skips_prune(policy_env, tmp_path, capsys, monkeypatch):
    from app.domains.policy.infrastructure.vectorstore.base import PolicyStoreError

    _seed_old(policy_env, "khong-xoa")
    prune_calls = _forbid_prune(monkeypatch, policy_env.store)
    real_replace = policy_env.store.replace_document

    def flaky_replace(doc, model, chunks, vectors):
        if doc.front.slug == "tai-lieu-a":
            raise PolicyStoreError("kho vector Milvus báo lỗi khi ghi tài liệu")
        return real_replace(doc, model, chunks, vectors)

    monkeypatch.setattr(policy_env.store, "replace_document", flaky_replace)
    _write_policy(tmp_path, "a.md", "tai-lieu-a")
    _write_policy(tmp_path, "b.md", "tai-lieu-b")

    code = main(["ingest-policies", str(tmp_path), "--prune"])

    assert code == 1
    captured = capsys.readouterr()
    assert "a.md" in captured.err and "lỗi khi nạp" in captured.err
    assert policy_env.store.get_document_meta("tai-lieu-b") is not None
    assert policy_env.store.get_document_meta("tai-lieu-a") is None
    assert prune_calls == []
    assert policy_env.store.get_document_meta("khong-xoa") is not None


@pytest.mark.parametrize(
    "module",
    [
        "app.domains.policy.infrastructure.embedding.gemini",
        "app.domains.policy.infrastructure.vectorstore.milvus_store",
    ],
)
def test_ingest_policies_missing_package_exits_2_with_a_clean_message_before_any_write(
    policy_env, tmp_path, capsys, monkeypatch, module
):
    import sys

    monkeypatch.setitem(sys.modules, module, None)  # import báo ImportError như khi chưa cài gói
    _seed_old(policy_env, "con-lai")
    _write_policy(tmp_path, "a.md", "tai-lieu-a")

    code = main(["ingest-policies", str(tmp_path), "--prune"])

    assert code == 2
    err = capsys.readouterr().err
    assert "requirements-chat.txt" in err and "Traceback" not in err
    assert "tai-lieu-a" not in err
    assert policy_env.embedder.calls == []
    assert policy_env.store.get_document_meta("tai-lieu-a") is None
    assert policy_env.store.get_document_meta("con-lai") is not None


def test_import_app_cli_does_not_import_gemini_sdk():
    code = "import sys, app.cli; bad = [m for m in sys.modules if m == 'google.genai' or m.startswith('google.genai.')]; assert not bad, bad"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=Path(__file__).parent.parent)

    assert result.returncode == 0, result.stderr
