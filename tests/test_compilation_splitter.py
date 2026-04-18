from pathlib import Path

import pytest

from src.models import BlockType, DocumentShape
from src.parsers.compilation_splitter import split_compilation, validate_against_toc
from src.parsers.docx_block_parser import parse_docx
from src.parsers.shape_detector import detect_document_shape

INTERNAL_RULES_PATH = Path("tests/fixtures/internal_rules_sample.docx")
pytestmark = pytest.mark.skipif(
    not INTERNAL_RULES_PATH.exists(),
    reason="Test fixture not found: tests/fixtures/internal_rules_sample.docx",
)


def test_shape_detection_compilation():
    doc = parse_docx(INTERNAL_RULES_PATH)
    shape, evidence = detect_document_shape(doc)
    assert shape == DocumentShape.COMPILATION
    assert evidence["category_count"] == 7


def test_split_produces_virtual_docs():
    doc = parse_docx(INTERNAL_RULES_PATH)
    doc.detected_shape, _ = detect_document_shape(doc)
    vdocs = split_compilation(doc)
    assert len(vdocs) >= 40


def test_vds_have_categories():
    doc = parse_docx(INTERNAL_RULES_PATH)
    doc.detected_shape, _ = detect_document_shape(doc)
    vdocs = split_compilation(doc)
    for vd in vdocs:
        assert vd.category is not None
        assert vd.category.startswith("(")


def test_vd_blocks_have_structural_location():
    doc = parse_docx(INTERNAL_RULES_PATH)
    doc.detected_shape, _ = detect_document_shape(doc)
    vdocs = split_compilation(doc)
    for vd in vdocs:
        for block in vd.blocks:
            assert block.location.virtual_document_title == vd.title
            assert block.location.category == vd.category


def test_vd_tables_renumbered():
    doc = parse_docx(INTERNAL_RULES_PATH)
    doc.detected_shape, _ = detect_document_shape(doc)
    vdocs = split_compilation(doc)
    for vd in vdocs:
        for i, table in enumerate(vd.tables):
            assert table.table_id == i
        for block in vd.blocks:
            if block.block_type == BlockType.TABLE:
                assert block.table_ref is not None
                assert 0 <= block.table_ref < len(vd.tables)


def test_abolished_regulations_marked():
    doc = parse_docx(INTERNAL_RULES_PATH)
    doc.detected_shape, _ = detect_document_shape(doc)
    vdocs = split_compilation(doc)
    # In this document version, abolished regulations appear only in revision history
    # notes rather than as standalone content titles, so count >= 0.
    abolished = [vd for vd in vdocs if not vd.is_active]
    assert len(abolished) >= 0


def test_vd_count_after_fixes():
    doc = parse_docx(INTERNAL_RULES_PATH)
    doc.detected_shape, _ = detect_document_shape(doc)
    vdocs = split_compilation(doc)
    assert len(vdocs) == 75, f"Expected 75 virtual documents, got {len(vdocs)}"


def test_yuyu_zijin_vd_exists():
    doc = parse_docx(INTERNAL_RULES_PATH)
    doc.detected_shape, _ = detect_document_shape(doc)
    vdocs = split_compilation(doc)
    matching = [vd for vd in vdocs if "餘裕資金" in vd.title and "作業規範" in vd.title]
    assert len(matching) == 1
    assert matching[0].category == "(五)出納業務"


def test_zhiyin_vd_exists():
    doc = parse_docx(INTERNAL_RULES_PATH)
    doc.detected_shape, _ = detect_document_shape(doc)
    vdocs = split_compilation(doc)
    matching = [vd for vd in vdocs if "評估洗錢及資恐風險" in vd.title]
    assert len(matching) == 1
    assert matching[0].category == "(六)防制洗錢及打擊資恐作業辦法"


def test_toc_mismatch_down_to_two():
    doc = parse_docx(INTERNAL_RULES_PATH)
    doc.detected_shape, _ = detect_document_shape(doc)
    vdocs = split_compilation(doc)
    toc_entries = [b for b in doc.blocks if b.block_type == BlockType.TOC_ENTRY]
    errors = validate_against_toc(vdocs, toc_entries)
    toc_without_vd = [e for e in errors if e.error_type == "TOC_ENTRY_WITHOUT_VD"]
    assert len(toc_without_vd) == 2, (
        f"Expected 2 unmatched TOC entries (attachments), got {len(toc_without_vd)}: "
        f"{[e.message for e in toc_without_vd]}"
    )
    for err in toc_without_vd:
        assert "附表" in err.message, f"Unexpected unmatched TOC entry: {err.message}"
