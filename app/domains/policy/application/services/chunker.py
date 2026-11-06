"""Cắt tài liệu chính sách (Markdown) thành chunk theo heading, để nhúng và truy hồi."""
import re
from dataclasses import dataclass

from app.domains.policy.application.services.corpus import PolicyDocument

PATH_SEPARATOR = " › "
DEFAULT_MAX_CHARS = 1000

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
# Ranh giới câu: sau `.`, `?`, `!` rồi tới khoảng trắng; ranh giới từ: mọi khoảng trắng.
_SENTENCE_BREAK = re.compile(r"(?<=[.?!])(\s+)")
_WORD_BREAK = re.compile(r"(\s+)")


@dataclass(frozen=True)
class PolicyChunk:
    index: int
    section_path: str
    text: str  # thân chunk, không kèm tiền tố đường dẫn mục

    @property
    def embed_text(self) -> str:
        return f"{self.section_path}\n\n{self.text}"


def chunk_document(doc: PolicyDocument, max_chars: int = DEFAULT_MAX_CHARS) -> list[PolicyChunk]:
    """Cắt `doc.body` thành chunk, mỗi chunk thuộc đúng một mục và `len(text) <= max_chars`.

    - `section_path` = `"<title> › <H2> › <H3>"` (bỏ cấp không có); title lấy từ front matter.
    - Dòng `# ...` (H1) chỉ là tên tài liệu, đã nằm trong đường dẫn nên bị bỏ khỏi văn bản.
      Văn bản trước heading `##` đầu tiên thuộc mục có đường dẫn chỉ là title.
    - Heading sâu hơn `###` (`####`, ...) không tạo mục mới: giữ nguyên làm văn bản của mục bao quanh.
    - Dòng bắt đầu bằng `#` trong khối mã ``` không phải heading; dòng trống trong khối mã không tách đoạn.
    - Mục không có thân bị bỏ. Không overlap giữa các chunk.
    - Đoạn = khối cách nhau bởi dòng trống (danh sách/bảng liền nhau là một đoạn). Các đoạn được gộp
      tới `max_chars`; đoạn dài hơn thì cắt tại ranh giới câu, câu dài hơn nữa cắt tại ranh giới từ
      (một từ dài hơn `max_chars` mới bị cắt cứng).
    """
    if max_chars < 1:
        raise ValueError("max_chars phải >= 1")
    chunks: list[PolicyChunk] = []
    for path, lines in _split_sections(doc.front.title, doc.body):
        for text in _pack_blocks(_split_blocks(lines), max_chars):
            chunks.append(PolicyChunk(index=len(chunks), section_path=path, text=text))
    return chunks


def _is_fence(line: str) -> bool:
    return line.lstrip().startswith("```")


def _split_sections(title: str, body: str) -> list[tuple[str, list[str]]]:
    """Duyệt dòng, giữ stack heading H2/H3; trả (section_path, các dòng thân) theo thứ tự xuất hiện."""
    sections: list[tuple[str, list[str]]] = []
    h2 = h3 = ""
    current: list[str] = []
    in_fence = False

    def path() -> str:
        return PATH_SEPARATOR.join(part for part in (title, h2, h3) if part)

    def flush() -> None:
        if any(line.strip() for line in current):
            sections.append((path(), list(current)))
        current.clear()

    for line in body.split("\n"):
        if _is_fence(line):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match is None:
            current.append(line)
            continue
        level, heading = len(match.group(1)), match.group(2)
        if level == 1:
            continue
        if level > 3:
            current.append(line)
            continue
        flush()
        if level == 2:
            h2, h3 = heading, ""
        else:
            h3 = heading
    flush()
    return sections


def _split_blocks(lines: list[str]) -> list[str]:
    """Tách thân mục thành đoạn theo dòng trống (không tách bên trong khối mã)."""
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in lines:
        if _is_fence(line):
            in_fence = not in_fence
        if not in_fence and not line.strip():
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _pack_blocks(blocks: list[str], max_chars: int) -> list[str]:
    """Gộp các đoạn liền nhau (nối bằng dòng trống) tới `max_chars`; đoạn quá dài được cắt riêng."""
    packed: list[str] = []
    current = ""
    for block in blocks:
        if len(block) > max_chars:
            if current:
                packed.append(current)
                current = ""
            packed.extend(_split_long(block, max_chars, (_SENTENCE_BREAK, _WORD_BREAK)))
            continue
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= max_chars:
            current = candidate
        else:
            packed.append(current)
            current = block
    if current:
        packed.append(current)
    return packed


def _split_long(text: str, max_chars: int, breaks: tuple[re.Pattern[str], ...]) -> list[str]:
    """Cắt `text` dài hơn `max_chars` tại ranh giới thô nhất còn dùng được (câu, rồi từ, rồi cắt cứng)."""
    if len(text) <= max_chars:
        return [text]
    if not breaks:
        return [text[start:start + max_chars] for start in range(0, len(text), max_chars)]

    parts = breaks[0].split(text)  # [đơn vị, khoảng trắng, đơn vị, ...]
    units = [parts[i] + (parts[i + 1] if i + 1 < len(parts) else "") for i in range(0, len(parts), 2)]
    pieces: list[str] = []
    current = ""
    for unit in units:
        if len((current + unit).rstrip()) <= max_chars:
            current += unit
            continue
        if current:
            pieces.append(current.rstrip())
            current = ""
        if len(unit.rstrip()) <= max_chars:
            current = unit
        else:
            pieces.extend(_split_long(unit.rstrip(), max_chars, breaks[1:]))
    if current.strip():
        pieces.append(current.rstrip())
    return pieces
