from pathlib import Path

import pytest

from src.models import BlockType, DocumentShape
from src.parsers.compilation_splitter import split_compilation
from src.parsers.docx_block_parser import parse_docx
from src.parsers.shape_detector import detect_document_shape

MANUAL_V1_PATH = Path("tests/fixtures/manual_vol1_sample.docx")
pytestmark = pytest.mark.skipif(
    not MANUAL_V1_PATH.exists(),
    reason="Test fixture not found: tests/fixtures/manual_vol1_sample.docx",
)


def test_manual_shape_is_narrative():
    doc = parse_docx(MANUAL_V1_PATH)
    shape, _ = detect_document_shape(doc)
    assert shape == DocumentShape.MANUAL_NARRATIVE


def test_manual_no_virtual_docs():
    doc = parse_docx(MANUAL_V1_PATH)
    doc.detected_shape, _ = detect_document_shape(doc)
    try:
        vdocs = split_compilation(doc)
        assert len(vdocs) == 0
    except ValueError as e:
        assert "COMPILATION" in str(e)


def test_manual_toc_entries_recognized():
    """TOC lines like「第一章 通則\t1」must be TOC_ENTRY, not CHAPTER/SUBSECTION_HEADING."""
    doc = parse_docx(MANUAL_V1_PATH)
    toc_entries = [b for b in doc.blocks if b.block_type == BlockType.TOC_ENTRY]

    chapter_like_toc = [
        b for b in toc_entries
        if b.content.startswith("第") and ("章" in b.content[:5] or "節" in b.content[:5])
    ]
    assert len(chapter_like_toc) >= 10, (
        f"Expected at least 10 '第X章/節...頁碼' TOC entries, got {len(chapter_like_toc)}"
    )

    has_first_chapter_toc = any(
        "第一章" in b.content and "通則" in b.content for b in toc_entries
    )
    assert has_first_chapter_toc, "目錄裡的「第一章 通則」應該是 TOC_ENTRY"


def test_manual_chapter_heading_count_reasonable():
    """Actual chapter headings in body content should be <= 6."""
    doc = parse_docx(MANUAL_V1_PATH)
    chapters = [b for b in doc.blocks if b.block_type == BlockType.CHAPTER_HEADING]
    assert len(chapters) <= 6, (
        f"Expected CHAPTER_HEADING <= 6, got {len(chapters)}: "
        f"{[b.content[:30] for b in chapters]}"
    )


def test_manual_subsection_count_reasonable():
    """Actual subsection headings in body content should be <= 50."""
    doc = parse_docx(MANUAL_V1_PATH)
    subs = [b for b in doc.blocks if b.block_type == BlockType.SUBSECTION_HEADING]
    assert len(subs) <= 50, (
        f"Expected SUBSECTION_HEADING <= 50, got {len(subs)}"
    )


def test_manual_has_tables():
    doc = parse_docx(MANUAL_V1_PATH)
    assert len(doc.tables) >= 5


def test_manual_blocks_have_location():
    doc = parse_docx(MANUAL_V1_PATH)
    for i, block in enumerate(doc.blocks):
        assert block.location.document_order_index == i


def test_manual_no_parse_errors():
    doc = parse_docx(MANUAL_V1_PATH)
    assert len(doc.parse_errors) == 0
