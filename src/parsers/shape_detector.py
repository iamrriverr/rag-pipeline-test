"""Heuristic document shape detection based on block type distribution."""
from src.models import BlockType, DocumentShape, ParsedDocument


def detect_document_shape(doc: ParsedDocument) -> tuple[DocumentShape, dict]:
    """Return (shape, evidence) where evidence contains block counts and decision rationale."""
    counts: dict[str, int] = {}
    for block in doc.blocks:
        key = block.block_type.value
        counts[key] = counts.get(key, 0) + 1

    total = len(doc.blocks)

    toc_heading_count = counts.get(BlockType.TOC_HEADING.value, 0)
    category_count = counts.get(BlockType.CATEGORY_HEADING.value, 0)
    regulation_title_count = counts.get(BlockType.REGULATION_TITLE.value, 0)
    table_count = counts.get(BlockType.TABLE.value, 0)
    chapter_heading_count = counts.get(BlockType.CHAPTER_HEADING.value, 0)
    point_count = counts.get(BlockType.POINT.value, 0)

    table_ratio = table_count / total if total > 0 else 0.0

    evidence = {
        "total_blocks": total,
        "toc_heading_count": toc_heading_count,
        "category_count": category_count,
        "regulation_title_count": regulation_title_count,
        "table_count": table_count,
        "table_ratio": round(table_ratio, 4),
        "chapter_heading_count": chapter_heading_count,
        "point_count": point_count,
        "block_type_counts": counts,
    }

    # Rule 1: COMPILATION — toc_heading is optional (some compilations omit it)
    if category_count >= 3 and regulation_title_count >= 5:
        evidence["decision"] = "COMPILATION: category>=3, regulation_title>=5"
        return DocumentShape.COMPILATION, evidence

    # Rule 2: MANUAL_SOP
    if table_count >= 10 and table_ratio > 0.2:
        evidence["decision"] = "MANUAL_SOP: table>=10 and table_ratio>0.2"
        return DocumentShape.MANUAL_SOP, evidence

    # Rule 3: MANUAL_NARRATIVE
    if chapter_heading_count >= 2 and table_ratio < 0.1:
        evidence["decision"] = "MANUAL_NARRATIVE: chapter>=2 and table_ratio<0.1"
        return DocumentShape.MANUAL_NARRATIVE, evidence

    # Rule 4: SINGLE_REGULATION
    if 1 <= regulation_title_count <= 2 and (chapter_heading_count + point_count) >= 3:
        evidence["decision"] = "SINGLE_REGULATION: regulation_title in 1-2, chapter+point>=3"
        return DocumentShape.SINGLE_REGULATION, evidence

    evidence["decision"] = "UNKNOWN: no rule matched"
    return DocumentShape.UNKNOWN, evidence
