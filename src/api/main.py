from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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
vlm_client = VLMClient() if settings.openai_api_key and settings.openai_api_key != "sk-xxx" else None
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


@app.post("/reset")
async def reset():
    deleted = store.clear()
    return {"deleted": deleted, "chunks_in_store": store.count}


# 靜態網頁 UI
_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/")
async def ui():
    return FileResponse(_static_dir / "index.html")
