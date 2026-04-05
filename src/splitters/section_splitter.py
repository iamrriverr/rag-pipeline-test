from src.models import Section


def split_by_heading(markdown: str, document_title: str = "") -> list[Section]:
    sections = []
    current_heading = ""
    current_level = 0
    current_lines = []

    for line in markdown.split('\n'):
        level, heading = _detect_heading(line)
        if level > 0:
            if current_heading or current_lines:
                sections.append(_make_section(
                    len(sections), current_heading, current_level, current_lines
                ))
            current_heading = heading
            current_level = level
            current_lines = []
        else:
            current_lines.append(line)

    if current_heading or current_lines:
        sections.append(_make_section(
            len(sections), current_heading, current_level, current_lines
        ))

    return sections


def _detect_heading(line: str) -> tuple[int, str]:
    if line.startswith('### '):
        return 3, line[4:].strip()
    if line.startswith('## '):
        return 2, line[3:].strip()
    if line.startswith('# '):
        return 1, line[2:].strip()
    return 0, ""


def _make_section(index: int, heading: str, level: int, lines: list[str]) -> Section:
    content = '\n'.join(lines).strip()
    return Section(
        section_index=index,
        heading=heading or f"Section {index}",
        heading_level=max(level, 1),
        content=content,
    )
