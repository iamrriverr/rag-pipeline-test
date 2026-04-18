"""Stage 1 v2 inspection tool.

Usage:
  uv run python scripts/inspect_stage1_v2.py <file_path>
"""
from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, ".")

from src.parsers.docx_block_parser import parse_docx
from src.parsers.compilation_splitter import split_compilation, validate_against_toc
from src.parsers.shape_detector import detect_document_shape
from src.models import BlockType, DocumentShape


def _safe_name(title: str, max_len: int = 30) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:max_len]


def inspect(file_path: str, output_dir: str = "data/inspect_v2") -> None:
    fp = Path(file_path)
    out = Path(output_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    print(f"[Stage 0] 複製原始檔案: {fp.name}")
    raw_dir = out / "00_raw"
    raw_dir.mkdir()
    shutil.copy(fp, raw_dir / fp.name)

    # ─── Stage 1: parse ────────────────────────────────────────────────────────
    print("[Stage 1] 解析 docx ...")
    doc = parse_docx(fp)
    parsed_data = json.loads(doc.model_dump_json())
    (out / "01_parsed_document.json").write_text(
        json.dumps(parsed_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  blocks={len(doc.blocks)}  tables={len(doc.tables)}  errors={len(doc.parse_errors)}")

    # ─── Stage 2: blocks ───────────────────────────────────────────────────────
    blocks_dir = out / "02_blocks"
    blocks_dir.mkdir()

    all_blocks = [json.loads(b.model_dump_json()) for b in doc.blocks]
    (blocks_dir / "all_blocks.json").write_text(
        json.dumps(all_blocks, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    dist = Counter(b.block_type.value for b in doc.blocks)
    dist_lines = [f"{bt}: {cnt}" for bt, cnt in sorted(dist.items())]
    (blocks_dir / "block_type_distribution.txt").write_text(
        "\n".join(dist_lines), encoding="utf-8"
    )
    print("[Stage 2] block_type_distribution:")
    for line in dist_lines:
        print(f"  {line}")

    human_lines: list[str] = []
    for b in doc.blocks:
        human_lines.append(
            f"## [{b.location.document_order_index}] {b.block_type.value}\n"
            f"content: {b.content[:120]}\n"
            f"location:\n"
            f"  source_paragraph_index: {b.location.source_paragraph_index}\n"
            f"  source_table_index:     {b.location.source_table_index}\n"
            f"  preceding_snippet:      {b.location.preceding_text_snippet}\n"
            f"  following_snippet:      {b.location.following_text_snippet}\n"
        )
    (blocks_dir / "blocks_with_location.md").write_text(
        "\n---\n".join(human_lines), encoding="utf-8"
    )

    # ─── Stage 3: tables ───────────────────────────────────────────────────────
    tables_dir = out / "03_tables"
    tables_dir.mkdir()

    tables_summary = []
    for t in doc.tables:
        tables_summary.append(
            {
                "table_id": t.table_id,
                "n_rows": t.n_rows,
                "n_cols": t.n_cols,
                "location": json.loads(t.location.model_dump_json()),
            }
        )
        tid = f"table_{t.table_id:03d}"
        (tables_dir / f"{tid}_grid.json").write_text(
            json.dumps(t.raw_grid, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (tables_dir / f"{tid}.md").write_text(t.markdown, encoding="utf-8")
        (tables_dir / f"{tid}.html").write_text(t.html, encoding="utf-8")

    (tables_dir / "tables_summary.json").write_text(
        json.dumps(tables_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[Stage 3] tables={len(doc.tables)}")

    # ─── Stage 4: shape ────────────────────────────────────────────────────────
    shape_dir = out / "04_shape"
    shape_dir.mkdir()

    shape, evidence = detect_document_shape(doc)
    doc.detected_shape = shape
    (shape_dir / "detection.json").write_text(
        json.dumps({"shape": shape.value, "evidence": evidence}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[Stage 4] shape={shape.value}")

    if shape != DocumentShape.COMPILATION:
        print("  (不是合訂本,跳過 Stage 5/6)")
        _write_summary(out, fp, doc, shape, [], [])
        return

    # ─── Stage 5: virtual docs ─────────────────────────────────────────────────
    vdocs_dir = out / "05_virtual_docs"
    vdocs_dir.mkdir()

    vdocs = split_compilation(doc)
    print(f"[Stage 5] virtual_docs={len(vdocs)}")

    summary_rows = []
    for vd in vdocs:
        summary_rows.append(
            {
                "order": vd.source_order_in_compilation,
                "title": vd.title,
                "category": vd.category,
                "is_active": vd.is_active,
                "abolished_note": vd.abolished_note,
                "establishment_date": vd.establishment_date_raw,
                "latest_revision_date": vd.latest_revision_date_raw,
                "blocks_count": len(vd.blocks),
                "tables_count": len(vd.tables),
            }
        )

        folder_name = f"{vd.source_order_in_compilation + 1:03d}_{_safe_name(vd.title)}"
        vd_dir = vdocs_dir / folder_name
        vd_dir.mkdir()

        (vd_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "title": vd.title,
                    "category": vd.category,
                    "is_active": vd.is_active,
                    "abolished_note": vd.abolished_note,
                    "establishment_date_raw": vd.establishment_date_raw,
                    "latest_revision_date_raw": vd.latest_revision_date_raw,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        vd_blocks = [json.loads(b.model_dump_json()) for b in vd.blocks]
        (vd_dir / "blocks.json").write_text(
            json.dumps(vd_blocks, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if vd.tables:
            tables_sub = vd_dir / "tables"
            tables_sub.mkdir()
            for t in vd.tables:
                tid = f"table_{t.table_id:03d}"
                (tables_sub / f"{tid}_grid.json").write_text(
                    json.dumps(t.raw_grid, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                (tables_sub / f"{tid}.md").write_text(t.markdown, encoding="utf-8")
                (tables_sub / f"{tid}.html").write_text(t.html, encoding="utf-8")

    (vdocs_dir / "summary.json").write_text(
        json.dumps({"count": len(vdocs), "items": summary_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ─── Stage 6: TOC validation ───────────────────────────────────────────────
    val_dir = out / "06_validation"
    val_dir.mkdir()

    toc_entries = [b for b in doc.blocks if b.block_type == BlockType.TOC_ENTRY]
    mismatch_errors = validate_against_toc(vdocs, toc_entries)
    (val_dir / "toc_mismatch.json").write_text(
        json.dumps(
            [json.loads(e.model_dump_json()) for e in mismatch_errors],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[Stage 6] toc_mismatch errors={len(mismatch_errors)}")

    _write_summary(out, fp, doc, shape, vdocs, mismatch_errors)


def _write_summary(out, fp, doc, shape, vdocs, errors) -> None:
    summary = {
        "file": str(fp),
        "blocks": len(doc.blocks),
        "tables": len(doc.tables),
        "parse_errors": len(doc.parse_errors),
        "shape": shape.value,
        "virtual_docs": len(vdocs),
        "toc_mismatch_count": len(errors),
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n=== 完成 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/inspect_stage1_v2.py <file_path>")
        sys.exit(1)
    inspect(sys.argv[1])
