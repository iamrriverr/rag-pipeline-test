# RAG Pipeline

## 技術棧

- **Parsing**: Docling + PyMuPDF + GPT-4o Vision (表格/流程圖)
- **Embedding**: OpenAI `text-embedding-3-small` (1536 維)
- **LLM**: OpenAI GPT
- **Vector DB**: Chroma (cosine)
- **Framework**: FastAPI + LangChain
- **UI**: Streamlit

## 快速開始

```bash
# 1. 安裝依賴
uv sync

# 2. 設定環境變數
cp .env.example .env
# 編輯 .env 填入 OPENAI_API_KEY

# 3. 跑測試
uv run pytest tests/
```

## 啟動方式

### Streamlit UI（推薦）

```bash
uv run streamlit run app.py
```

瀏覽器打開 <http://localhost:8501>，含文件上傳、對話、知識庫管理。

### FastAPI

```bash
uv run uvicorn src.api.main:app --reload --port 3000
```

瀏覽器打開 <http://localhost:3000>，含簡易上傳/對話介面。

## 結構

```
├── app.py             # Streamlit UI
├── src/
│   ├── parsers/       # Stage 1: 文件解析（PDF/DOCX/MD/TXT/CSV/XLSX）
│   ├── vlm/           # GPT-4o Vision 處理表格與流程圖
│   ├── cleaners/      # Stage 2: 文本清洗（CJK 空白、法規結構、PII 遮罩）
│   ├── splitters/     # Stage 3: 分塊（Section）+ 切片（Chunk）+ breadcrumb
│   ├── vectorstore/   # Stage 4: Chroma 持久化
│   ├── pipeline/      # Stage 1-4 串接
│   ├── retriever/     # Stage 5: 向量檢索 + Section 上下文補全
│   ├── generator/     # Stage 6: RAG 問答（含引用來源）
│   └── api/           # FastAPI endpoints + 靜態 UI
├── scripts/
│   └── inspect_stages.py  # 逐 Stage 檢查工具
└── tests/
```

## Heading 階層（法規文件）

```
法規標題 (#)  ← 例如「汐止區農會信用部個人資料檔案安全維護管理辦法」
  章 (##)    ← 第一章、第二章...
    條 (###) ← 第一條、第二條...
```

## 開發工具

```bash
# 逐 Stage 檢查（不呼叫 VLM）
uv run python scripts/inspect_stages.py path/to/file.pdf

# 啟用 GPT-4o Vision 處理表格/圖片
uv run python scripts/inspect_stages.py path/to/file.pdf --with-vlm
```

輸出會在 `data/inspect/` 或 `data/inspect_vlm/` 逐階段產生檔案，方便除錯。

## API Endpoints

| Method | Path | 說明 |
|---|---|---|
| GET  | `/`        | Web UI |
| POST | `/upload`  | 上傳檔案並 ingest |
| POST | `/chat`    | 問答（form: `query`） |
| GET  | `/status`  | 向量庫目前 chunk 數 |
| POST | `/reset`   | 清空向量庫 |
