from pathlib import Path

import pytest

from src.models import BlockType, FileType, ParsedDocument
from src.parsers.docx_block_parser import parse_docx

INTERNAL_RULES_PATH = Path("tests/fixtures/internal_rules_sample.docx")
pytestmark = pytest.mark.skipif(
    not INTERNAL_RULES_PATH.exists(),
    reason="Test fixture not found: tests/fixtures/internal_rules_sample.docx",
)


def test_parse_returns_parsed_document():
    doc = parse_docx(INTERNAL_RULES_PATH)
    assert isinstance(doc, ParsedDocument)
    assert doc.file_type == FileType.DOCX
    assert doc.source_hash


def test_blocks_have_order_index():
    doc = parse_docx(INTERNAL_RULES_PATH)
    for i, block in enumerate(doc.blocks):
        assert block.location.document_order_index == i


def test_blocks_have_location_info():
    doc = parse_docx(INTERNAL_RULES_PATH)
    with_source = sum(
        1
        for b in doc.blocks
        if b.location.source_paragraph_index is not None
        or b.location.source_table_index is not None
    )
    assert with_source / len(doc.blocks) >= 0.9


def test_content_snippets_populated():
    doc = parse_docx(INTERNAL_RULES_PATH)
    middle_blocks = doc.blocks[10:-10]
    with_preceding = sum(1 for b in middle_blocks if b.location.preceding_text_snippet)
    assert with_preceding / len(middle_blocks) >= 0.8


def test_identifies_toc():
    doc = parse_docx(INTERNAL_RULES_PATH)
    toc_entries = [b for b in doc.blocks if b.block_type == BlockType.TOC_ENTRY]
    assert len(toc_entries) >= 50


def test_identifies_categories():
    doc = parse_docx(INTERNAL_RULES_PATH)
    cats = [b for b in doc.blocks if b.block_type == BlockType.CATEGORY_HEADING]
    assert len(cats) == 7


def test_identifies_regulation_titles():
    doc = parse_docx(INTERNAL_RULES_PATH)
    reg_titles = [b for b in doc.blocks if b.block_type == BlockType.REGULATION_TITLE]
    assert len(reg_titles) >= 40


def test_identifies_dates():
    doc = parse_docx(INTERNAL_RULES_PATH)
    est = [b for b in doc.blocks if b.block_type == BlockType.ESTABLISHMENT_DATE]
    assert len(est) >= 30


def test_tables_have_three_formats():
    doc = parse_docx(INTERNAL_RULES_PATH)
    assert len(doc.tables) > 0
    for table in doc.tables:
        assert table.raw_grid, f"table {table.table_id} has empty raw_grid"
        assert table.markdown, f"table {table.table_id} has empty markdown"
        assert table.html, f"table {table.table_id} has empty html"
        assert "<table>" in table.html


def test_table_blocks_have_ref():
    doc = parse_docx(INTERNAL_RULES_PATH)
    table_blocks = [b for b in doc.blocks if b.block_type == BlockType.TABLE]
    for tb in table_blocks:
        assert tb.table_ref is not None
        assert 0 <= tb.table_ref < len(doc.tables)


def test_tables_have_location():
    doc = parse_docx(INTERNAL_RULES_PATH)
    for table in doc.tables:
        assert table.location.document_order_index >= 0


def test_cross_line_title_merged():
    doc = parse_docx(INTERNAL_RULES_PATH)
    titles = [b.content for b in doc.blocks if b.block_type == BlockType.REGULATION_TITLE]
    matching = [t for t in titles if "餘裕資金" in t and "作業規範" in t]
    assert len(matching) >= 1, (
        f"Expected merged title, got titles containing '餘裕資金': "
        f"{[t for t in titles if '餘裕資金' in t]}"
    )


def test_zhiyin_suffix_recognized():
    doc = parse_docx(INTERNAL_RULES_PATH)
    titles = [b.content for b in doc.blocks if b.block_type == BlockType.REGULATION_TITLE]
    matching = [t for t in titles if "評估洗錢及資恐風險" in t and t.endswith("指引")]
    assert len(matching) >= 1, (
        f"Expected title ending with '指引', got: {[t for t in titles if '評估' in t]}"
    )
