from src.splitters.section_splitter import split_by_heading
from src.splitters.breadcrumb import build_breadcrumbs
from src.splitters.chunk_splitter import split_section_to_chunks
from src.splitters.metadata import extract_inline_metadata


def test_split_by_heading():
    md = "# 章一\n內容一\n## 節一\n小節內容\n# 章二\n內容二"
    sections = split_by_heading(md)
    assert len(sections) == 3
    assert sections[0].heading == "章一"
    assert sections[1].heading_level == 2
    assert sections[2].heading == "章二"


def test_build_breadcrumbs():
    md = "# 章一\n\n## 節一\n\n### 小節A\n\n## 節二"
    sections = split_by_heading(md)
    bcs = build_breadcrumbs(sections, document_title="測試文件")
    assert bcs[0] == "測試文件 > 章一"
    assert bcs[1] == "測試文件 > 章一 > 節一"
    assert bcs[2] == "測試文件 > 章一 > 節一 > 小節A"
    assert bcs[3] == "測試文件 > 章一 > 節二"


def test_split_section_small():
    md = "# 小節\n短內容"
    sections = split_by_heading(md)
    chunks = split_section_to_chunks(sections[0])
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0


def test_extract_inline_metadata():
    raw = '# METADATA={"department": "信用部"}\n# 主標題\n內容'
    meta, rest = extract_inline_metadata(raw)
    assert meta == {"department": "信用部"}
    assert rest.startswith("# 主標題")

    meta2, rest2 = extract_inline_metadata("# 主標題\n內容")
    assert meta2 == {}
    assert rest2.startswith("# 主標題")
