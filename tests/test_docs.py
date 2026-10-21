import re
from pathlib import Path

from app.domains.quotation.application.services.ingest.schema import QuotationFile

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
TOOLS = [
    "get_quotation", "find_quotations", "get_work_item", "search_work_items", "compare_work_item_price",
    "compare_work_item_detail", "get_project_overview", "compare_labor_cost",
    "compare_project_cost_breakdown", "run_readonly_sql",
]


def test_readme_mentions_all_ten_tools():
    assert [tool for tool in TOOLS if tool not in README] == []


def _code_blocks(text: str) -> list[str]:
    return re.findall(r"```[a-z]*\n(.*?)```", text, flags=re.DOTALL)


def test_readme_commands_reference_existing_files():
    path_pattern = re.compile(r"(?<![\w/.-])((?:scripts|data|docs|app|tests)/[\w./-]+|docker-compose\.yml|main(?:_mcp)?\.py)")
    missing = []
    for block in _code_blocks(README):
        for match in path_pattern.findall(block):
            if not (ROOT / match.rstrip("/.")).exists():
                missing.append(match)
    assert missing == []


def test_readme_links_point_to_existing_files():
    links = re.findall(r"\]\(((?!https?://|#)[^)\s]+)\)", README)
    assert links, "README phải có liên kết tới tài liệu"
    assert [link for link in links if not (ROOT / link.split("#")[0]).exists()] == []


def test_readme_is_vietnamese_and_has_core_sections():
    for heading in ("## Dự án này là gì", "## Vì sao có ích", "## Chạy thử", "## Ví dụ hỏi đáp thật", "## Giấy phép"):
        assert heading in README, heading


def test_readme_has_at_least_three_real_examples():
    examples = sorted((ROOT / "docs" / "examples").glob("*.md"))

    assert len(examples) >= 3
    for example in examples:
        assert f"docs/examples/{example.name}" in README


def test_data_format_doc_lists_every_top_level_key():
    doc = (ROOT / "docs" / "data-format.md").read_text(encoding="utf-8")

    assert [key for key in QuotationFile.model_fields if f"`{key}`" not in doc] == []


def test_claude_md_exists():
    assert "knowledge_base" in (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def test_readme_warns_that_compose_up_reloads_sample_data():
    assert "nạp lại dữ liệu mẫu" in README


def test_concept_metadata_matches_the_enforced_vocabulary():
    from app.domains.quotation.application.services.ingest.concepts import CONCEPT_VOCABULARY

    doc = (ROOT / "app" / "domains" / "quotation" / "metadata" / "concept.yaml").read_text(encoding="utf-8")

    missing = [f"{kind}: {name}" for kind, names in CONCEPT_VOCABULARY.items() for name in names if name not in doc]
    assert missing == []


def test_data_format_doc_describes_duplicate_handling():
    doc = (ROOT / "docs" / "data-format.md").read_text(encoding="utf-8")

    for phrase in ("unchanged", "on_conflict=replace", "--replace", "content_hash", "409"):
        assert phrase in doc, phrase


def test_readme_has_a_disclaimer_that_brands_and_data_are_invented():
    assert "## Tuyên bố miễn trừ" in README
    section = README.split("## Tuyên bố miễn trừ", 1)[1].split("\n## ", 1)[0]

    for phrase in ("thương hiệu", "tự bịa", "ngẫu nhiên", "Vietcoat", "không liên quan"):
        assert phrase in section, phrase
    assert "(#tuyên-bố-miễn-trừ)" in README.split("## Tuyên bố miễn trừ", 1)[0]


def test_readme_documents_the_terminal_chat():
    for phrase in ("python -m app.chat", "GEMINI_API_KEY", "requirements-chat.txt", "chat_logs", "/clear"):
        assert phrase in README, phrase


def test_compose_chat_service_passes_through_every_documented_chat_switch():
    """Compose không tự chuyển biến môi trường máy chủ vào container: mỗi biến CHAT_* người vận hành đổi được (README) phải nằm trong `environment` của `chat`."""
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    chat_block = compose.split("\n  chat:\n", 1)[1]
    documented = set(re.findall(r"^\| `(CHAT_[A-Z_]+)`", README, flags=re.MULTILINE))
    operator_switches = documented - {"CHAT_API_HOST", "CHAT_API_PORT"}  # hai biến này cố định trong compose (host/cổng)

    assert {"CHAT_DEMO_ENABLED", "CHAT_MAX_QUESTION_CHARS", "CHAT_MAX_TURNS_PER_SESSION"} <= operator_switches
    assert [name for name in sorted(operator_switches) if f"{name}: ${{{name}:-" not in chat_block] == []
