# 農會 RAG Pipeline — MVP 開發指南

## 範圍

只做核心 Pipeline：**文件進 → 向量出 → 問答回**。

```
包含：
  ✓ 文件上傳 + 格式路由（PDF/DOCX/MD/TXT）
  ✓ Docling 解析 + VLM 三通道
  ✓ 文本清洗（7 步）
  ✓ 分塊(Section) + 切片(Chunk) + 兩層 metadata
  ✓ bge-large-zh embedding + Chroma 寫入
  ✓ 混合檢索（向量 + BM25）+ section 上下文補全
  ✓ LLM RAG 問答 + 引用來源
  ✓ 簡易 FastAPI endpoint（上傳 + 問答）
  ✓ Inspect 工作流（逐 Stage 檢查）

不包含：
  ✗ Auth / JWT / 權限過濾
  ✗ 部門管理 / 人員管理
  ✗ E-form 電子表單
  ✗ 標準答案 / 預設提問 / 回饋
  ✗ boost / 版本管理 / 批次刪除
  ✗ PostgreSQL（MVP 用 Chroma 單庫 + 本地 JSON 追蹤）
```

---

## 環境

```bash
# 安裝
uv init farmer-rag && cd farmer-rag
uv add fastapi uvicorn chromadb langchain langchain-community langchain-chroma \
       langchain-ollama docling python-multipart pydantic-settings \
       pandas openpyxl PyMuPDF tenacity

uv add --dev pytest httpx

# Ollama 模型
ollama pull bge-large-zh-v1.5
ollama pull qwen3.5:9b
```

```bash
# .env
CHROMA_PATH=./data/chroma
STORAGE_PATH=./data/uploads
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=bge-large-zh-v1.5
LLM_MODEL=qwen3.5:9b
OPENAI_API_KEY=sk-xxx          # VLM 用（GPT-4o Vision）
BGE_QUERY_PREFIX=为这个句子生成表示以用于检索相关文章：
CHUNK_MAX_CHARS=800
CHUNK_TARGET_CHARS=600
CHUNK_OVERLAP=100
```

---

## 目錄結構

```
farmer-rag/
├── .env
├── pyproject.toml
│
├── src/
│   ├── config.py              # Settings
│   ├── models.py              # Pydantic schemas（全部放一個檔案）
│   │
│   ├── parsers/               # Stage 1
│   │   ├── __init__.py
│   │   ├── router.py          # detect_file_type()
│   │   ├── docling_parser.py  # Docling + VLM 三通道
│   │   ├── text_parser.py     # TXT → Markdown
│   │   ├── table_parser.py    # CSV/XLSX → Markdown
│   │   └── parser.py          # DocumentParser（統一入口）
│   │
│   ├── vlm/                   # VLM 呼叫（獨立，方便 mock）
│   │   ├── __init__.py
│   │   ├── client.py          # VLMClient
│   │   └── prompts.py         # table_prompt, image_prompt
│   │
│   ├── cleaners/              # Stage 2
│   │   ├── __init__.py
│   │   ├── cjk.py
│   │   ├── headers.py
│   │   ├── legal.py
│   │   ├── pii.py
│   │   ├── dedup.py
│   │   └── pipeline.py        # clean_all()
│   │
│   ├── splitters/             # Stage 3
│   │   ├── __init__.py
│   │   ├── section_splitter.py
│   │   ├── chunk_splitter.py
│   │   ├── breadcrumb.py
│   │   ├── quality.py
│   │   └── metadata.py        # extract_inline_metadata()
│   │
│   ├── vectorstore/           # Stage 4
│   │   ├── __init__.py
│   │   └── chroma_store.py    # ChromaStore
│   │
│   ├── pipeline/              # Stage 1→4 串接
│   │   ├── __init__.py
│   │   └── ingest.py          # IngestPipeline.run()
│   │
│   ├── retriever/             # Stage 5
│   │   ├── __init__.py
│   │   ├── hybrid.py          # HybridRetriever
│   │   └── context.py         # expand_context()
│   │
│   ├── generator/             # Stage 6
│   │   ├── __init__.py
│   │   ├── prompts.py         # RAG_PROMPT
│   │   └── rag.py             # RAGGenerator
│   │
│   └── api/                   # 簡易 API（不含 Auth）
│       ├── __init__.py
│       └── main.py            # FastAPI app + 2 個 endpoint
│
├── scripts/
│   └── inspect.py             # 逐 Stage 檢查
│
├── tests/
│   ├── conftest.py
│   ├── test_cleaners.py
│   ├── test_splitters.py
│   ├── test_pipeline.py
│   └── fixtures/
│       ├── sample.pdf
│       └── sample.md
│
└── data/
    ├── uploads/               # 原始檔案
    ├── chroma/                # Chroma 持久化
    └── inspect/               # inspect 輸出
```

---

## 模組實作

### config.py

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    chroma_path: str = "./data/chroma"
    storage_path: str = "./data/uploads"
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "bge-large-zh-v1.5"
    embedding_dim: int = 1024
    llm_model: str = "qwen3.5:9b"
    openai_api_key: str = ""
    bge_query_prefix: str = "为这个句子生成表示以用于检索相关文章："
    chunk_max_chars: int = 800
    chunk_target_chars: int = 600
    chunk_overlap: int = 100

    class Config:
        env_file = ".env"

settings = Settings()
```

---

### models.py

```python
from enum import Enum
from pydantic import BaseModel
from uuid import UUID, uuid4

class FileType(str, Enum):
    PDF = "PDF"
    DOCX = "DOCX"
    MARKDOWN = "MARKDOWN"
    TXT = "TXT"
    CSV = "CSV"
    XLSX = "XLSX"
    ARCHIVE = "ARCHIVE"
    UNSUPPORTED = "UNSUPPORTED"

class ContentType(str, Enum):
    TEXT = "TEXT"
    VLM_TABLE = "VLM_TABLE"
    VLM_IMAGE = "VLM_IMAGE"
    SKIPPED = "SKIPPED"

class Section(BaseModel):
    id: UUID = None
    section_index: int
    heading: str
    heading_level: int
    breadcrumb: str = ""
    content: str
    content_type: ContentType = ContentType.TEXT
    page_numbers: list[int] = []
    char_count: int = 0
    vlm_confidence: float | None = None

    def model_post_init(self, __context):
        if self.id is None:
            self.id = uuid4()
        if self.char_count == 0:
            self.char_count = len(self.content)

class Chunk(BaseModel):
    id: UUID = None
    section_id: UUID
    document_id: UUID | None = None
    chunk_index: int
    global_index: int = 0
    total_chunks_in_section: int
    breadcrumb: str
    content: str               # [breadcrumb] + 原文，送 embedding
    content_raw: str           # 不帶前綴的原文
    char_count: int = 0
    has_overlap_before: bool = False

    # Section 層資訊（攤平，寫入 Chroma metadata）
    heading: str = ""
    heading_level: int = 0
    content_type: ContentType = ContentType.TEXT

    def model_post_init(self, __context):
        if self.id is None:
            self.id = uuid4()
        if self.char_count == 0:
            self.char_count = len(self.content_raw)

class ChunkMetadata(BaseModel):
    """寫入 Chroma 的 metadata。"""
    document_id: str
    document_title: str
    department: str = ""
    section_id: str
    section_index: int
    heading: str
    heading_level: int
    breadcrumb: str
    content_type: str
    chunk_index: int
    global_index: int
    total_chunks_in_section: int
    embedding_model: str

class Reference(BaseModel):
    document_id: str
    document_title: str
    heading: str
    breadcrumb: str
    chunk_id: str
    content: str
    relevance_score: float
    page_numbers: list[int] = []

class RAGResponse(BaseModel):
    answer: str
    references: list[Reference]
    confidence: str    # high / medium / low / not_found
```

---

### parsers/router.py

```python
from pathlib import Path
from src.models import FileType

MIME_MAP = {
    ".pdf": FileType.PDF,
    ".docx": FileType.DOCX, ".doc": FileType.DOCX,
    ".md": FileType.MARKDOWN, ".mdx": FileType.MARKDOWN,
    ".txt": FileType.TXT, ".log": FileType.TXT,
    ".csv": FileType.CSV, ".tsv": FileType.CSV,
    ".xlsx": FileType.XLSX, ".xls": FileType.XLSX,
    ".rar": FileType.ARCHIVE, ".zip": FileType.ARCHIVE,
}

def detect_file_type(filename: str) -> FileType:
    suffix = Path(filename).suffix.lower()
    return MIME_MAP.get(suffix, FileType.UNSUPPORTED)
```

---

### parsers/docling_parser.py

```python
from pathlib import Path
from docling.document_converter import DocumentConverter
from docling.datamodel.document import TableItem, PictureItem
import fitz
from src.models import ContentType
from src.vlm.client import VLMClient


class DoclingParser:
    """Docling 版面分析 + VLM 三通道。"""

    def __init__(self, vlm_client: VLMClient | None = None):
        self._converter = DocumentConverter()
        self._vlm = vlm_client

    def parse(self, file_path: Path) -> list[dict]:
        """回傳 [{content, content_type, page_no, vlm_confidence}, ...]"""
        result = self._converter.convert(str(file_path))
        doc = result.document
        pdf_doc = fitz.open(str(file_path)) if file_path.suffix == '.pdf' else None

        parts = []
        for item, _level in doc.iterate_items():
            if isinstance(item, TableItem) and self._vlm:
                page_no = item.prov[0].page_no if item.prov else 0
                page_img = self._rasterize_page(pdf_doc, page_no)
                text = self._vlm.table_to_text(page_img)
                parts.append({
                    "content": text,
                    "content_type": ContentType.VLM_TABLE,
                    "page_no": page_no,
                    "vlm_confidence": 0.9,  # TODO: 從 VLM 回應取
                })

            elif isinstance(item, PictureItem) and self._vlm:
                page_no = item.prov[0].page_no if item.prov else 0
                page_img = self._rasterize_page(pdf_doc, page_no)
                text = self._vlm.image_to_text(page_img)
                parts.append({
                    "content": text,
                    "content_type": ContentType.VLM_IMAGE,
                    "page_no": page_no,
                    "vlm_confidence": 0.85,
                })

            else:
                if hasattr(item, 'text') and item.text:
                    page_no = item.prov[0].page_no if hasattr(item, 'prov') and item.prov else 0
                    parts.append({
                        "content": item.text,
                        "content_type": ContentType.TEXT,
                        "page_no": page_no,
                        "vlm_confidence": None,
                    })

        if pdf_doc:
            pdf_doc.close()
        return parts

    def _rasterize_page(self, pdf_doc, page_no: int, dpi: int = 200) -> bytes:
        """將 PDF 頁面轉為 PNG bytes。"""
        if not pdf_doc:
            return b""
        page = pdf_doc[page_no]
        pix = page.get_pixmap(dpi=dpi)
        return pix.tobytes("png")
```

---

### parsers/parser.py（統一入口）

```python
from pathlib import Path
from src.models import FileType
from src.parsers.router import detect_file_type
from src.parsers.docling_parser import DoclingParser
from src.vlm.client import VLMClient
from src.splitters.metadata import extract_inline_metadata
import pandas as pd
import re


class DocumentParser:
    def __init__(self, vlm_client: VLMClient | None = None):
        self._docling = DoclingParser(vlm_client)

    def parse(self, file_path: Path) -> tuple[str, FileType, dict]:
        """回傳 (markdown, file_type, inline_metadata)"""
        file_type = detect_file_type(file_path.name)

        match file_type:
            case FileType.PDF | FileType.DOCX:
                parts = self._docling.parse(file_path)
                md = "\n\n".join(p["content"] for p in parts if p["content"])
            case FileType.MARKDOWN:
                md = file_path.read_text(encoding="utf-8")
            case FileType.TXT:
                md = self._parse_txt(file_path)
            case FileType.CSV:
                md = self._parse_csv(file_path)
            case FileType.XLSX:
                md = self._parse_xlsx(file_path)
            case _:
                raise ValueError(f"不支援: {file_path.suffix}")

        inline_meta, md = extract_inline_metadata(md)
        return md, file_type, inline_meta

    def _parse_txt(self, path: Path) -> str:
        raw = path.read_text(encoding="utf-8")
        raw = re.sub(r'^(第[一二三四五六七八九十百]+章)\s*(.+)$',
                     r'# \1 \2', raw, flags=re.MULTILINE)
        raw = re.sub(r'^(第[一二三四五六七八九十百]+條)\s*',
                     r'## \1 ', raw, flags=re.MULTILINE)
        return raw

    def _parse_csv(self, path: Path) -> str:
        df = pd.read_csv(path)
        return f"## {path.stem}\n\n{df.to_markdown(index=False)}"

    def _parse_xlsx(self, path: Path) -> str:
        sheets = pd.read_excel(path, sheet_name=None)
        parts = []
        for name, df in sheets.items():
            parts.append(f"## {name}\n\n{df.to_markdown(index=False)}")
        return "\n\n".join(parts)
```

---

### vlm/client.py

```python
from openai import OpenAI
import base64
from src.config import settings
from src.vlm.prompts import TABLE_PROMPT, IMAGE_PROMPT


class VLMClient:
    def __init__(self):
        self._client = OpenAI(api_key=settings.openai_api_key)

    def table_to_text(self, image_bytes: bytes) -> str:
        return self._call(image_bytes, TABLE_PROMPT)

    def image_to_text(self, image_bytes: bytes) -> str:
        return self._call(image_bytes, IMAGE_PROMPT)

    def _call(self, image_bytes: bytes, system_prompt: str) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        response = self._client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{b64}"
                    }}
                ]}
            ],
            max_tokens=2000,
        )
        return response.choices[0].message.content
```

---

### vlm/prompts.py

```python
TABLE_PROMPT = """你是文件表格轉換專家。請將圖片中的表格轉換為結構化的 Markdown 格式。
規則：
1. 保留所有欄位和數值，不可省略。
2. 合併儲存格需完整展開。
3. 勾選框：□ → 未勾選，■/☑ → 已勾選。
4. 如果表格是角色對應表（如客戶/櫃員/主管），用描述式 Markdown 列出每個角色的職責。
5. 輸出繁體中文。"""

IMAGE_PROMPT = """你是文件流程圖轉換專家。請將圖片中的流程圖或 SOP 轉換為步驟化描述。
格式：
步驟 1：[執行者] — [動作]
  → 條件：[判斷條件]
  → 是：前往步驟 2
  → 否：前往步驟 3
輸出繁體中文。"""
```

---

### cleaners/pipeline.py

```python
import re
import hashlib
from collections import Counter


def fix_cjk_spacing(text: str) -> str:
    return re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', text)

def remove_repeated_headers(text: str, threshold: int = 3) -> str:
    lines = text.split('\n')
    counts = Counter(line.strip() for line in lines if line.strip())
    repeated = {line for line, c in counts.items() if c >= threshold and len(line) < 50}
    return '\n'.join(line for line in lines if line.strip() not in repeated)

def detect_legal_structure(text: str) -> str:
    text = re.sub(r'^(第[一二三四五六七八九十百]+章)\s*(.+)$',
                  r'# \1 \2', text, flags=re.MULTILINE)
    text = re.sub(r'^(第[一二三四五六七八九十百]+條)\s*',
                  r'## \1 ', text, flags=re.MULTILINE)
    return text

def mask_pii(text: str) -> str:
    text = re.sub(r'([A-Z])\d{5}(\d{4})', r'\1*****\2', text)
    text = re.sub(r'(09\d{2})\d{3}(\d{3})', r'\1***\2', text)
    return text

def compute_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def clean_all(text: str) -> str:
    text = fix_cjk_spacing(text)
    text = remove_repeated_headers(text)
    text = detect_legal_structure(text)
    text = mask_pii(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
```

---

### splitters/section_splitter.py

```python
from uuid import uuid4
from src.models import Section, ContentType


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
```

---

### splitters/chunk_splitter.py

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter
from src.models import Chunk, Section
from src.config import settings


def split_section_to_chunks(section: Section) -> list[Chunk]:
    content = section.content

    if len(content) <= settings.chunk_max_chars:
        return [Chunk(
            section_id=section.id,
            chunk_index=0,
            total_chunks_in_section=1,
            breadcrumb=section.breadcrumb,
            content=f"[{section.breadcrumb}] {content}" if section.breadcrumb else content,
            content_raw=content,
            heading=section.heading,
            heading_level=section.heading_level,
            content_type=section.content_type,
        )]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_target_chars,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", "。", "；", " "],
    )
    texts = splitter.split_text(content)

    return [Chunk(
        section_id=section.id,
        chunk_index=i,
        total_chunks_in_section=len(texts),
        breadcrumb=section.breadcrumb,
        content=f"[{section.breadcrumb}] {t}" if section.breadcrumb else t,
        content_raw=t,
        has_overlap_before=i > 0,
        heading=section.heading,
        heading_level=section.heading_level,
        content_type=section.content_type,
    ) for i, t in enumerate(texts)]
```

---

### splitters/breadcrumb.py

```python
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
```

---

### vectorstore/chroma_store.py

```python
import chromadb
from src.config import settings
from src.models import Chunk, ChunkMetadata


class ChromaStore:
    def __init__(self, path: str = None, collection_name: str = "farmer_chunks"):
        self._client = chromadb.PersistentClient(path=path or settings.chroma_path)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def add_chunks(self, chunks: list[Chunk], vectors: list[list[float]],
                   metadatas: list[dict]) -> list[str]:
        ids = [str(c.id) for c in chunks]
        self._collection.add(
            ids=ids,
            embeddings=vectors,
            documents=[c.content for c in chunks],
            metadatas=metadatas,
        )
        return ids

    def query(self, query_embedding: list[float], k: int = 5,
              where: dict = None) -> dict:
        kwargs = {"query_embeddings": [query_embedding], "n_results": k,
                  "include": ["documents", "metadatas", "distances"]}
        if where:
            kwargs["where"] = where
        return self._collection.query(**kwargs)

    def get_by_section(self, section_id: str) -> dict:
        return self._collection.get(
            where={"section_id": section_id},
            include=["documents", "metadatas"]
        )

    def delete_by_document(self, document_id: str):
        self._collection.delete(where={"document_id": document_id})

    @property
    def count(self) -> int:
        return self._collection.count()
```

---

### pipeline/ingest.py

```python
from pathlib import Path
from uuid import uuid4
from src.config import settings
from src.models import Chunk, ChunkMetadata, FileType
from src.parsers.parser import DocumentParser
from src.cleaners.pipeline import clean_all, compute_file_hash
from src.splitters.section_splitter import split_by_heading
from src.splitters.chunk_splitter import split_section_to_chunks
from src.splitters.breadcrumb import build_breadcrumbs
from src.splitters.quality import check_quality
from src.vectorstore.chroma_store import ChromaStore
from langchain_ollama import OllamaEmbeddings
from tenacity import retry, wait_exponential, stop_after_attempt


class IngestPipeline:
    def __init__(self, parser: DocumentParser, store: ChromaStore):
        self._parser = parser
        self._store = store
        self._embedder = OllamaEmbeddings(
            model=settings.embedding_model,
            base_url=settings.ollama_base_url,
        )

    def run(self, file_path: Path, title: str = "", department: str = "") -> dict:
        document_id = str(uuid4())
        file_path = Path(file_path)
        title = title or file_path.stem

        # Stage 1: 解析
        markdown, file_type, inline_meta = self._parser.parse(file_path)
        department = inline_meta.get("department", department)

        # Stage 2: 清洗
        cleaned = clean_all(markdown)

        # Stage 3: 分塊
        sections = split_by_heading(cleaned, document_title=title)
        breadcrumbs = build_breadcrumbs(sections, document_title=title)
        for section, bc in zip(sections, breadcrumbs):
            section.breadcrumb = bc

        # Stage 3: 切片
        all_chunks: list[Chunk] = []
        global_index = 0
        for section in sections:
            chunks = split_section_to_chunks(section)
            for chunk in chunks:
                chunk.document_id = uuid4()  # 用同一個
                chunk.global_index = global_index
                global_index += 1
            all_chunks.extend(chunks)
            section.char_count = sum(c.char_count for c in chunks)

        # 修正 document_id
        for chunk in all_chunks:
            chunk.document_id = document_id

        # 品質檢查
        issues = check_quality(all_chunks)

        # Stage 4: Embedding
        contents = [c.content for c in all_chunks]
        vectors = self._embed_batch(contents)

        # Stage 4: 寫入 Chroma
        metadatas = [self._build_metadata(c, document_id, title, department) for c in all_chunks]
        chroma_ids = self._store.add_chunks(all_chunks, vectors, metadatas)

        return {
            "document_id": document_id,
            "title": title,
            "file_type": file_type.value,
            "section_count": len(sections),
            "chunk_count": len(all_chunks),
            "quality_issues": len(issues),
            "sections": [{"heading": s.heading, "chunk_count": len(split_section_to_chunks(s))}
                         for s in sections],
        }

    @retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.embed_documents(texts)

    def _build_metadata(self, chunk: Chunk, doc_id: str,
                        title: str, department: str) -> dict:
        return ChunkMetadata(
            document_id=doc_id,
            document_title=title,
            department=department,
            section_id=str(chunk.section_id),
            section_index=0,  # TODO: 從 section 取
            heading=chunk.heading,
            heading_level=chunk.heading_level,
            breadcrumb=chunk.breadcrumb,
            content_type=chunk.content_type.value,
            chunk_index=chunk.chunk_index,
            global_index=chunk.global_index,
            total_chunks_in_section=chunk.total_chunks_in_section,
            embedding_model=settings.embedding_model,
        ).model_dump()
```

---

### retriever/hybrid.py

```python
from langchain_community.retrievers import BM25Retriever
from langchain_ollama import OllamaEmbeddings
from src.config import settings
from src.vectorstore.chroma_store import ChromaStore
from src.retriever.context import expand_context


class HybridRetriever:
    def __init__(self, store: ChromaStore):
        self._store = store
        self._embedder = OllamaEmbeddings(
            model=settings.embedding_model,
            base_url=settings.ollama_base_url,
        )

    def retrieve(self, query: str, k: int = 5) -> list[dict]:
        # 向量檢索（帶 bge query prefix）
        prefixed_query = settings.bge_query_prefix + query
        query_vec = self._embedder.embed_query(prefixed_query)
        vector_results = self._store.query(query_vec, k=k * 2)

        # 整理結果
        results = []
        for i in range(len(vector_results["ids"][0])):
            meta = vector_results["metadatas"][0][i]
            results.append({
                "chunk_id": vector_results["ids"][0][i],
                "content": vector_results["documents"][0][i],
                "distance": vector_results["distances"][0][i],
                "metadata": meta,
            })

        # 按距離排序，取 top-k
        results.sort(key=lambda x: x["distance"])
        top_k = results[:k]

        # Section 上下文補全
        for r in top_k:
            expanded = expand_context(self._store, r["metadata"])
            if expanded:
                r["expanded_content"] = expanded

        return top_k
```

---

### retriever/context.py

```python
from src.vectorstore.chroma_store import ChromaStore


def expand_context(store: ChromaStore, chunk_metadata: dict) -> str | None:
    if chunk_metadata.get("total_chunks_in_section", 1) <= 1:
        return None

    result = store.get_by_section(chunk_metadata["section_id"])
    if not result or not result["documents"]:
        return None

    # 按 chunk_index 排序合併
    pairs = list(zip(result["metadatas"], result["documents"]))
    pairs.sort(key=lambda p: p[0].get("chunk_index", 0))
    return "\n".join(doc for _, doc in pairs)
```

---

### generator/prompts.py

```python
RAG_SYSTEM_PROMPT = """你是農會信用部的合規知識助手。請嚴格遵守以下規則：
1. 只根據「參考資料」中的內容回答問題，不可使用自身知識補充。
2. 回答時必須標註資料來源（文件名稱、章節）。
3. 如果參考資料中沒有相關內容，請直接回答「我在知識庫中未找到相關資料」。
4. 引用法規條文時需完整引用原文，不可改寫或概括。"""

RAG_USER_TEMPLATE = """問題：{question}

參考資料：
{context}

請根據以上參考資料回答問題，並標註引用來源。"""
```

---

### generator/rag.py

```python
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from src.config import settings
from src.models import RAGResponse, Reference
from src.retriever.hybrid import HybridRetriever
from src.generator.prompts import RAG_SYSTEM_PROMPT, RAG_USER_TEMPLATE


class RAGGenerator:
    def __init__(self, retriever: HybridRetriever, use_openai: bool = False):
        self._retriever = retriever
        if use_openai:
            self._llm = ChatOpenAI(model="gpt-4o", api_key=settings.openai_api_key)
        else:
            self._llm = ChatOllama(
                model=settings.llm_model,
                base_url=settings.ollama_base_url,
                temperature=0.0,
            )

    def answer(self, question: str, k: int = 5) -> RAGResponse:
        # 檢索
        results = self._retriever.retrieve(question, k=k)

        if not results:
            return RAGResponse(
                answer="我在知識庫中未找到相關資料。",
                references=[],
                confidence="not_found",
            )

        # 組裝 context
        context_parts = []
        for r in results:
            content = r.get("expanded_content") or r["content"]
            meta = r["metadata"]
            context_parts.append(
                f"[來源：{meta['document_title']} > {meta['heading']}]\n{content}"
            )
        context = "\n\n---\n\n".join(context_parts)

        # LLM 生成
        messages = [
            ("system", RAG_SYSTEM_PROMPT),
            ("human", RAG_USER_TEMPLATE.format(question=question, context=context)),
        ]
        response = self._llm.invoke(messages)
        answer_text = response.content

        # 組裝 references
        references = [
            Reference(
                document_id=r["metadata"]["document_id"],
                document_title=r["metadata"]["document_title"],
                heading=r["metadata"]["heading"],
                breadcrumb=r["metadata"]["breadcrumb"],
                chunk_id=r["chunk_id"],
                content=r["content"][:200],
                relevance_score=round(1 - r["distance"], 3),
            )
            for r in results
        ]

        confidence = "high" if results[0]["distance"] < 0.3 else \
                     "medium" if results[0]["distance"] < 0.5 else "low"

        return RAGResponse(
            answer=answer_text,
            references=references,
            confidence=confidence,
        )
```

---

### api/main.py

```python
from fastapi import FastAPI, UploadFile, File, Form
from pathlib import Path
import shutil
from src.config import settings
from src.models import FileType
from src.parsers.parser import DocumentParser
from src.parsers.router import detect_file_type
from src.vlm.client import VLMClient
from src.vectorstore.chroma_store import ChromaStore
from src.pipeline.ingest import IngestPipeline
from src.retriever.hybrid import HybridRetriever
from src.generator.rag import RAGGenerator

app = FastAPI(title="Farmer RAG API", version="MVP")

# 初始化
vlm_client = VLMClient() if settings.openai_api_key else None
parser = DocumentParser(vlm_client)
store = ChromaStore()
pipeline = IngestPipeline(parser, store)
retriever = HybridRetriever(store)
generator = RAGGenerator(retriever)


@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    department: str = Form(""),
):
    # 檢查檔案類型
    file_type = detect_file_type(file.filename)
    if file_type == FileType.UNSUPPORTED:
        return {"error": f"不支援的檔案類型: {file.filename}"}

    # 存檔
    upload_dir = Path(settings.storage_path)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / file.filename
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 跑 Pipeline
    result = pipeline.run(file_path, title=title or file.filename, department=department)
    return result


@app.post("/chat")
async def chat(query: str = Form(...)):
    result = generator.answer(query)
    return result.model_dump()


@app.get("/status")
async def status():
    return {"chunks_in_store": store.count}
```

```bash
# 啟動
uvicorn src.api.main:app --reload --port 3000
```

---

### scripts/inspect.py

```python
"""逐 Stage 檢查一份文件的處理結果。"""
from pathlib import Path
import json, sys, shutil

sys.path.insert(0, ".")
from src.parsers.parser import DocumentParser
from src.cleaners.pipeline import clean_all
from src.splitters.section_splitter import split_by_heading
from src.splitters.chunk_splitter import split_section_to_chunks
from src.splitters.breadcrumb import build_breadcrumbs
from src.splitters.quality import check_quality
from src.splitters.metadata import extract_inline_metadata


def inspect(file_path: str, output_dir: str = "data/inspect"):
    out = Path(output_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # Stage 0: 原始檔案
    (out / "00_raw").mkdir()
    shutil.copy(file_path, out / "00_raw/")
    print(f"[Stage 0] 原始檔案: {file_path}")

    # Stage 1: 解析
    parser = DocumentParser()  # 不帶 VLM（inspect 不花錢）
    md, file_type, inline_meta = parser.parse(Path(file_path))
    (out / "01_parsed").mkdir()
    (out / "01_parsed/full.md").write_text(md, encoding="utf-8")
    (out / "01_parsed/metadata.json").write_text(
        json.dumps({"file_type": file_type.value, "inline_meta": inline_meta},
                    ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Stage 1] 解析完成: {len(md)} chars, type={file_type.value}")

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
    print(f"\n=== 完成 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/inspect.py <file_path>")
    else:
        inspect(sys.argv[1])
```

---

### splitters/quality.py

```python
from src.models import Chunk


def check_quality(chunks: list[Chunk], min_chars: int = 50,
                  max_chars: int = 2000) -> list[tuple[Chunk, str]]:
    issues = []
    for chunk in chunks:
        if chunk.char_count < min_chars:
            issues.append((chunk, "too_short"))
        elif chunk.char_count > max_chars:
            issues.append((chunk, "too_long"))
    return issues
```

---

### splitters/metadata.py

```python
import json, re


def extract_inline_metadata(content: str) -> tuple[dict, str]:
    pattern = r'^(?:#|<!--)\s*METADATA=({.*?})\s*(?:-->)?\s*\n'
    match = re.match(pattern, content)
    if match:
        return json.loads(match.group(1)), content[match.end():]
    return {}, content
```

---

## 開發順序

```
Step 1: config + models + cleaners + splitters
  → uv run python -c "from src.cleaners.pipeline import clean_all; print(clean_all('開 戶 第一章 總則'))"
  → uv run pytest tests/test_cleaners.py tests/test_splitters.py

Step 2: parsers（不含 VLM）
  → uv run python scripts/inspect.py tests/fixtures/sample.pdf
  → 檢查 data/inspect/ 每個 Stage 的輸出

Step 3: vectorstore + pipeline/ingest.py
  → uv run python -c "
    from src.pipeline.ingest import IngestPipeline
    from src.parsers.parser import DocumentParser
    from src.vectorstore.chroma_store import ChromaStore
    p = IngestPipeline(DocumentParser(), ChromaStore())
    print(p.run('tests/fixtures/sample.pdf'))
  "

Step 4: retriever + generator
  → uv run python -c "
    from src.retriever.hybrid import HybridRetriever
    from src.generator.rag import RAGGenerator
    from src.vectorstore.chroma_store import ChromaStore
    store = ChromaStore()
    r = HybridRetriever(store)
    g = RAGGenerator(r)
    print(g.answer('開戶需要什麼文件？').model_dump())
  "

Step 5: api/main.py
  → uvicorn src.api.main:app --reload --port 3000
  → curl -X POST http://localhost:3000/upload -F "file=@tests/fixtures/sample.pdf"
  → curl -X POST http://localhost:3000/chat -F "query=開戶需要什麼文件？"
```

每一步都可以獨立驗證，不需要等後面的模組。
