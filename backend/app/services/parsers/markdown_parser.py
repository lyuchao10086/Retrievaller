import re
from typing import Any


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def parse_markdown_document(
    markdown_text: str,
    document_id: str,
    knowledge_base_id: str,
    file_name: str,
    file_type: str,
) -> dict[str, Any]:
    """把 Markdown 文本解析成可追溯章节结构。

    当前阶段只识别 Markdown 标题层级，不做 chunk、不做向量化。
    """
    sections: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None
    content_lines: list[str] = []
    chapter: str | None = None
    section: str | None = None
    subsection: str | None = None

    for line in markdown_text.splitlines():
        heading = HEADING_PATTERN.match(line)
        if heading is None:
            if current_section is not None:
                content_lines.append(line)
            continue

        if current_section is not None:
            current_section["content"] = _normalize_content(content_lines)
            sections.append(current_section)

        level = len(heading.group(1))
        title = heading.group(2).strip()
        if level == 1:
            chapter = title
            section = None
            subsection = None
        elif level == 2:
            section = title
            subsection = None
        elif level >= 3:
            subsection = title

        current_section = {
            "level": level,
            "title": title,
            "content": "",
            "chapter": chapter,
            "section": section,
            "subsection": subsection,
        }
        content_lines = []

    if current_section is not None:
        current_section["content"] = _normalize_content(content_lines)
        sections.append(current_section)

    return {
        "document_id": document_id,
        "knowledge_base_id": knowledge_base_id,
        "file_name": file_name,
        "file_type": file_type,
        "parser": "markdown",
        "sections": sections,
    }


def _normalize_content(lines: list[str]) -> str:
    """去掉章节内容首尾空行，同时保留段落内部换行。"""
    content = "\n".join(lines).strip()
    return content
