"""Split a compiled regulation document into individual VirtualDocuments."""
from __future__ import annotations

import copy
import re
from typing import Optional

from src.models import (
    Block,
    BlockType,
    DocumentShape,
    ParseError,
    ParsedDocument,
    TableRecord,
    VirtualDocument,
)

_RE_TOC_PAGE = re.compile(r"^(.+?)(\t|[ \u3000\.]{2,})(\d{1,4})\s*$")
_ABOLISHED_MARKERS = ["(整併後廢止)", "整併後廢止", "(廢止)", "廢止"]


def _parse_toc_entry(text: str) -> tuple[str, Optional[int]]:
    m = _RE_TOC_PAGE.match(text)
    if m:
        return m.group(1).strip(), int(m.group(3))
    return text.strip(), None


def _find_content_start(blocks: list[Block]) -> int:
    """Return the list index of the first block that is part of regulation content."""
    # Look for a top-level SECTION_HEADING — must NOT be a full regulation title.
    # Use short, non-title keywords that only appear in compilation dividers.
    _TOP_LEVEL_KEYWORDS = ["業務規章", "業務類", "業務規範"]
    for i, block in enumerate(blocks):
        if block.block_type == BlockType.SECTION_HEADING and any(
            kw in block.content and len(block.content) < 20
            for kw in _TOP_LEVEL_KEYWORDS
        ):
            return i + 1

    # Fallback: first CATEGORY_HEADING (always precedes first regulation group)
    for i, block in enumerate(blocks):
        if block.block_type == BlockType.CATEGORY_HEADING:
            return i

    # Last resort: first REGULATION_TITLE
    for i, block in enumerate(blocks):
        if block.block_type == BlockType.REGULATION_TITLE:
            return i

    return 0


def validate_against_toc(
    virtual_docs: list[VirtualDocument], toc_entries: list[Block]
) -> list[ParseError]:
    errors: list[ParseError] = []

    # Filter out category-level entries (e.g. "(一) 業務類") — these appear in the TOC
    # but correspond to CATEGORY_HEADING blocks, not VirtualDocuments.
    _RE_TOC_CATEGORY = re.compile(r"^\([一二三四五六七八九十]\)")
    toc_titles = {
        _parse_toc_entry(b.content)[0]
        for b in toc_entries
        if not _RE_TOC_CATEGORY.match(b.content.strip())
    }
    vd_titles = {vd.title for vd in virtual_docs}

    for title in toc_titles:
        if title and title not in vd_titles:
            # Prefix match: handles wrapped titles where the auto-TOC only captures
            # the first paragraph (heading style), but the VD uses the merged full title.
            if not any(vd_t.startswith(title) for vd_t in vd_titles):
                errors.append(
                    ParseError(
                        error_type="TOC_ENTRY_WITHOUT_VD",
                        message=f"TOC entry '{title}' has no corresponding VirtualDocument",
                        severity="WARNING",
                    )
                )

    for title in vd_titles:
        if title not in toc_titles:
            # Prefix match: VD title is a completion of a partial TOC entry
            if not any(title.startswith(toc_t) for toc_t in toc_titles):
                errors.append(
                    ParseError(
                        error_type="VD_WITHOUT_TOC_ENTRY",
                    message=f"VirtualDocument '{title}' has no TOC entry",
                    severity="WARNING",
                )
            )

    return errors


def split_compilation(doc: ParsedDocument) -> list[VirtualDocument]:
    """Split a COMPILATION ParsedDocument into individual VirtualDocuments.

    Raises ValueError if doc.detected_shape is not COMPILATION.
    """
    if doc.detected_shape != DocumentShape.COMPILATION:
        raise ValueError(
            f"Expected COMPILATION shape, got {doc.detected_shape}. "
            "Run detect_document_shape first and assign to doc.detected_shape."
        )

    toc_entries = [b for b in doc.blocks if b.block_type == BlockType.TOC_ENTRY]
    toc_map: dict[str, int] = {}
    for b in toc_entries:
        title, page = _parse_toc_entry(b.content)
        if title and page is not None:
            toc_map[title] = page

    content_start = _find_content_start(doc.blocks)

    virtual_docs: list[VirtualDocument] = []
    current_category: Optional[str] = None
    current_vd: Optional[VirtualDocument] = None
    vd_order = 0

    def push_vd() -> None:
        nonlocal current_vd
        if current_vd is not None:
            virtual_docs.append(current_vd)
            current_vd = None

    for block in doc.blocks[content_start:]:
        btype = block.block_type

        if btype == BlockType.CATEGORY_HEADING:
            current_category = block.content
            # Do NOT push current_vd here — categories span multiple regulations
            if current_vd is not None:
                current_vd.blocks.append(block)
            continue

        if btype == BlockType.REGULATION_TITLE:
            push_vd()

            is_active = True
            abolished_note: Optional[str] = None
            for marker in _ABOLISHED_MARKERS:
                if marker in block.content:
                    is_active = False
                    abolished_note = marker
                    break

            current_vd = VirtualDocument(
                title=block.content,
                category=current_category,
                source_file_path=doc.source_path,
                source_file_hash=doc.source_hash,
                source_order_in_compilation=vd_order,
                is_active=is_active,
                abolished_note=abolished_note,
            )
            vd_order += 1
            current_vd.blocks.append(block)
            continue

        if current_vd is None:
            continue

        if btype == BlockType.ESTABLISHMENT_DATE:
            current_vd.establishment_date_raw = block.content
            current_vd.blocks.append(block)
            continue

        if btype == BlockType.REVISION_DATE:
            current_vd.latest_revision_date_raw = block.content  # last one wins
            current_vd.blocks.append(block)
            continue

        if btype == BlockType.TABLE:
            # Copy table from doc.tables and renumber within vd
            if block.table_ref is not None and block.table_ref < len(doc.tables):
                orig_table = doc.tables[block.table_ref]
                new_table_id = len(current_vd.tables)
                new_table = orig_table.model_copy(update={"table_id": new_table_id})
                current_vd.tables.append(new_table)
                # Update block's table_ref to the vd-local id
                updated_block = block.model_copy(update={"table_ref": new_table_id})
                current_vd.blocks.append(updated_block)
            else:
                current_vd.blocks.append(block)
            continue

        current_vd.blocks.append(block)

    push_vd()

    # Fill structural path fields on every block
    for vd in virtual_docs:
        page_ref = toc_map.get(vd.title)
        for i, block in enumerate(vd.blocks):
            block.location.virtual_document_title = vd.title
            block.location.category = vd.category
            # TODO: fill section_breadcrumb in next stage (chapter/article splitting)
            if i == 0 and page_ref is not None:
                block.location.compilation_page_reference = page_ref

    return virtual_docs
