from src.models import Section


def build_breadcrumbs(sections: list[Section], document_title: str = "") -> list[str]:
    stack = []
    if document_title:
        stack.append((0, document_title))

    breadcrumbs = []
    for section in sections:
        level = section.heading_level
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, section.heading))
        breadcrumbs.append(" > ".join(text for _, text in stack))

    return breadcrumbs
