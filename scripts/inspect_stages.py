"""逐 Stage 檢查一份文件的處理結果。

用法：
  uv run python scripts/inspect_stages.py <file_path>               # 不呼叫 VLM
  uv run python scripts/inspect_stages.py <file_path> --with-vlm    # 啟用 GPT-4o Vision 轉表格/圖片
"""
from pathlib import Path
import json
import sys
import shutil

sys.path.insert(0, ".")
from src.parsers.parser import DocumentParser
from src.cleaners.pipeline import clean_all
from src.splitters.section_splitter import split_by_heading
from src.splitters.chunk_splitter import split_section_to_chunks
from src.splitters.breadcrumb import build_breadcrumbs
from src.splitters.quality import check_quality


def inspect(file_path: str, output_dir: str = "data/inspect", with_vlm: bool = False):
    out = Path(output_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # Stage 0: 原始檔案
    (out / "00_raw").mkdir()
    shutil.copy(file_path, out / "00_raw/")
    print(f"[Stage 0] 原始檔案: {file_path}  (with_vlm={with_vlm})")

    # Stage 1: 解析
    vlm_client = None
    if with_vlm:
        from src.vlm.client import VLMClient
        from src.config import settings
        if not settings.openai_api_key or settings.openai_api_key == "sk-xxx":
            print("[Stage 1] 警告: OPENAI_API_KEY 未設定，VLM 無法啟用")
        else:
            vlm_client = VLMClient()
            print("[Stage 1] VLM 已啟用 (GPT-4o Vision)")
    parser = DocumentParser(vlm_client)
    md, file_type, inline_meta = parser.parse(Path(file_path))
    (out / "01_parsed").mkdir()
    (out / "01_parsed/full.md").write_text(md, encoding="utf-8")
    (out / "01_parsed/metadata.json").write_text(
        json.dumps({"file_type": file_type.value, "inline_meta": inline_meta},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Stage 1] 解析完成: {len(md)} chars, type={file_type.value}")

    # Stage 1.5: 若為 PDF/DOCX，額外輸出每個 block 的 content_type（含 VLM 標記）
    if file_type.value in ("PDF", "DOCX"):
        from src.parsers.docling_parser import DoclingParser
        parts = DoclingParser(vlm_client).parse(Path(file_path))
        blocks_dir = out / "01_parsed" / "blocks"
        blocks_dir.mkdir()
        summary_rows = []
        for i, p in enumerate(parts):
            ct = p["content_type"].value if hasattr(p["content_type"], "value") else str(p["content_type"])
            fname = f"{i:03d}_{ct}_p{p['page_no']}.md"
            (blocks_dir / fname).write_text(p["content"] or "", encoding="utf-8")
            summary_rows.append({
                "index": i,
                "content_type": ct,
                "page_no": p["page_no"],
                "chars": len(p["content"] or ""),
                "vlm_confidence": p.get("vlm_confidence"),
            })
        (out / "01_parsed/blocks_summary.json").write_text(
            json.dumps(summary_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        counts = {}
        for r in summary_rows:
            counts[r["content_type"]] = counts.get(r["content_type"], 0) + 1
        print(f"[Stage 1.5] Block 類型分布: {counts}")

    # Stage 2: 清洗
    cleaned = clean_all(md)
    (out / "02_cleaned").mkdir()
    (out / "02_cleaned/cleaned.md").write_text(cleaned, encoding="utf-8")
    print(f"[Stage 2] 清洗完成: {len(cleaned)} chars")

    # Stage 3: 分塊
    sections = split_by_heading(cleaned)
    breadcrumbs = build_breadcrumbs(sections, document_title=Path(file_path).stem)
    for s, bc in zip(sections, breadcrumbs):
        s.breadcrumb = bc

    (out / "03_sections").mkdir()
    for i, s in enumerate(sections):
        fname = f"{i:02d}_{s.heading[:20].replace('/', '_')}.md"
        (out / f"03_sections/{fname}").write_text(
            f"# {s.heading}\nbreadcrumb: {s.breadcrumb}\n"
            f"level: {s.heading_level}\nchars: {s.char_count}\n\n{s.content}",
            encoding="utf-8")
    print(f"[Stage 3] 分塊完成: {len(sections)} sections")

    # Stage 3: 切片
    (out / "04_chunks").mkdir()
    all_chunks = []
    global_idx = 0
    for s in sections:
        chunks = split_section_to_chunks(s)
        for c in chunks:
            c.global_index = global_idx
            fname = f"{global_idx:03d}_s{s.section_index}_c{c.chunk_index}.md"
            (out / f"04_chunks/{fname}").write_text(c.content, encoding="utf-8")
            global_idx += 1
        all_chunks.extend(chunks)

    issues = check_quality(all_chunks)
    (out / "04_chunks/quality.json").write_text(
        json.dumps([{
            "global_index": c.global_index,
            "char_count": c.char_count,
            "issue": issue,
        } for c, issue in issues], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Stage 3] 切片完成: {len(all_chunks)} chunks, {len(issues)} issues")

    # 總結
    summary = {
        "file": str(file_path),
        "file_type": file_type.value,
        "raw_chars": len(md),
        "cleaned_chars": len(cleaned),
        "sections": len(sections),
        "chunks": len(all_chunks),
        "quality_issues": len(issues),
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== 完成 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/inspect_stages.py <file_path> [--with-vlm]")
        sys.exit(1)
    args = sys.argv[1:]
    with_vlm = "--with-vlm" in args
    file_arg = next(a for a in args if not a.startswith("--"))
    out_dir = "data/inspect_vlm" if with_vlm else "data/inspect"
    inspect(file_arg, output_dir=out_dir, with_vlm=with_vlm)
