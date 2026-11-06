"""Kiểm tra tĩnh docker-compose.yml cho profile `rag` (Milvus + policy-seed); không cần chạy container."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT / "docker-compose.yml"
SERVICES = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))["services"]


def test_db_image_is_unchanged():
    assert SERVICES["db"]["image"] == "postgres:16"


def test_rag_services_only_run_with_the_rag_profile():
    assert SERVICES["milvus"]["profiles"] == ["rag"]
    assert SERVICES["policy-seed"]["profiles"] == ["rag"]
    # các service mặc định không được kéo theo Milvus (nếu không `docker compose up` thường sẽ bật nó)
    for name in ("db", "seed", "api", "mcp"):
        assert "profiles" not in SERVICES[name], name
        assert "milvus" not in (SERVICES[name].get("depends_on") or {}), name


def test_milvus_image_is_pinned_to_an_explicit_version():
    image = SERVICES["milvus"]["image"]
    assert re.fullmatch(r"milvusdb/milvus:v\d+\.\d+\.\d+", image), image


def test_milvus_is_a_single_container_with_embedded_etcd_and_local_storage():
    milvus = SERVICES["milvus"]
    env = milvus["environment"]

    assert milvus["command"] == ["milvus", "run", "standalone"]
    assert str(env["ETCD_USE_EMBED"]).lower() == "true"
    assert env["ETCD_DATA_DIR"] == "/var/lib/milvus/etcd"
    assert env["COMMON_STORAGETYPE"] == "local"
    assert "milvus_data:/var/lib/milvus" in milvus["volumes"]
    assert "milvus_data" in yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))["volumes"]


def test_milvus_ports_are_loopback_only_and_only_grpc_is_published():
    assert SERVICES["milvus"]["ports"] == ["127.0.0.1:19530:19530"]


def test_milvus_healthcheck_uses_healthz():
    check = SERVICES["milvus"]["healthcheck"]

    assert "/healthz" in " ".join(check["test"])
    assert "start_period" in check  # Milvus khởi động chậm; không có start_period thì retries cạn trước khi sẵn sàng


def test_policy_seed_waits_for_milvus_and_runs_the_idempotent_ingest():
    seed = SERVICES["policy-seed"]

    assert seed["depends_on"]["milvus"]["condition"] == "service_healthy"
    assert seed["environment"]["MILVUS_URI"] == "http://milvus:19530"
    assert "GEMINI_API_KEY" in seed["environment"]
    assert seed["command"] == "python -m app.cli ingest-policies data/policies --prune"
    assert seed["restart"] == "no"
    assert seed["image"] == SERVICES["seed"]["image"]  # dùng chung image ứng dụng


def test_mcp_gets_milvus_uri_and_gemini_key_for_query_time_embedding():
    mcp = SERVICES["mcp"]
    env = mcp["environment"]

    assert env["MILVUS_URI"] == "${MILVUS_URI:-http://milvus:19530}"
    assert env["GEMINI_API_KEY"] == "${GEMINI_API_KEY:-}"
    # chờ policy-seed nếu profile rag bật, nhưng không bắt buộc khi profile tắt
    assert mcp["depends_on"]["policy-seed"] == {"condition": "service_completed_successfully", "required": False}
    assert mcp["depends_on"]["seed"]["condition"] == "service_completed_successfully"


def test_header_comment_mentions_the_rag_profile():
    header = COMPOSE_FILE.read_text(encoding="utf-8").split("x-app:", 1)[0]
    assert "--profile rag" in header


@pytest.mark.skipif(shutil.which("docker") is None, reason="không có docker")
@pytest.mark.parametrize("profiles", [[], ["rag"], ["rag", "chat"]], ids=["default", "rag", "rag+chat"])
def test_docker_compose_config_is_valid(profiles):
    command = ["docker", "compose", "-f", str(COMPOSE_FILE)]
    for profile in profiles:
        command += ["--profile", profile]
    result = subprocess.run(command + ["config", "-q"], capture_output=True, text=True, timeout=60, cwd=ROOT)

    if result.returncode != 0 and "compose" in result.stderr.lower() and "not a docker command" in result.stderr.lower():
        pytest.skip("docker compose plugin không có")
    assert result.returncode == 0, result.stderr
