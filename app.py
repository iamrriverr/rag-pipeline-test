"""Farmer RAG — Streamlit UI"""
import streamlit as st
from pathlib import Path

from src.config import settings
from src.models import FileType
from src.parsers.parser import DocumentParser
from src.parsers.router import detect_file_type
from src.vlm.client import VLMClient
from src.vectorstore.chroma_store import ChromaStore
from src.pipeline.ingest import IngestPipeline
from src.retriever.hybrid import HybridRetriever
from src.generator.rag import RAGGenerator

# ── 頁面設定 ──
st.set_page_config(page_title="Farmer RAG", page_icon="📚", layout="wide")


# ── 初始化（快取，只建立一次）──
@st.cache_resource
def init_pipeline():
    vlm_client = None
    if settings.openai_api_key and settings.openai_api_key != "sk-xxx":
        vlm_client = VLMClient()
    parser = DocumentParser(vlm_client)
    store = ChromaStore()
    pipeline_obj = IngestPipeline(parser, store)
    retriever = HybridRetriever(store)
    generator_obj = RAGGenerator(retriever)
    return store, pipeline_obj, generator_obj


store, pipeline, generator = init_pipeline()

# ── Session state ──
if "messages" not in st.session_state:
    st.session_state.messages = []


# ── 渲染函式 ──
def render_answer(data: dict):
    """渲染 RAG 回答：confidence + 回答 + 參考來源。"""
    conf = data.get("confidence", "")
    color_map = {"high": "green", "medium": "orange", "low": "red", "not_found": "gray"}
    color = color_map.get(conf, "gray")
    st.markdown(f":{color}[**{conf.upper()}**]")
    st.markdown(data["answer"])
    refs = data.get("references", [])
    if refs:
        with st.expander(f"📖 參考來源（{len(refs)}）", expanded=False):
            for r in refs:
                score_pct = r["relevance_score"] * 100
                st.markdown(
                    f"**{r['breadcrumb']}**  \n"
                    f"`{score_pct:.1f}%` — {r['content'][:150]}..."
                )
                st.divider()


# ── Sidebar：上傳 + 知識庫管理 ──
with st.sidebar:
    st.title("📚 Farmer RAG")

    # 知識庫狀態
    st.subheader("知識庫狀態")
    st.metric("Chunks", store.count)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 重整"):
            st.rerun()
    with col2:
        if st.button("🗑️ 清空", type="secondary"):
            deleted = store.clear()
            st.toast(f"已刪除 {deleted} 個 chunks")
            st.rerun()

    st.divider()

    # 文件上傳
    st.subheader("上傳文件")
    uploaded_file = st.file_uploader(
        "選擇檔案",
        type=["pdf", "docx", "md", "txt", "csv", "xlsx"],
    )
    title = st.text_input("文件標題（可選）", placeholder="留空則用檔名")
    department = st.text_input("部門（可選）", placeholder="例如：信用部")

    if uploaded_file and st.button("📤 上傳並 Ingest", type="primary", use_container_width=True):
        file_type = detect_file_type(uploaded_file.name)
        if file_type == FileType.UNSUPPORTED:
            st.error(f"不支援的檔案類型: {uploaded_file.name}")
        else:
            upload_dir = Path(settings.storage_path)
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_path = upload_dir / uploaded_file.name
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            with st.spinner("正在處理文件（解析 → 清洗 → 分塊 → Embedding）..."):
                try:
                    result = pipeline.run(
                        file_path,
                        title=title or uploaded_file.name,
                        department=department,
                    )
                    st.success(
                        f"✅ Ingest 完成！\n\n"
                        f"- 標題：{result['title']}\n"
                        f"- 類型：{result['file_type']}\n"
                        f"- Sections: {result['section_count']}\n"
                        f"- Chunks: {result['chunk_count']}\n"
                        f"- 品質問題: {result['quality_issues']}"
                    )
                    with st.expander("詳細結果"):
                        st.json(result)
                except Exception as e:
                    st.error(f"處理失敗：{e}")

    st.divider()
    if st.button("🧹 清除對話紀錄", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


# ── 主區域：對話 ──
st.header("💬 對話")

# 顯示歷史訊息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and "raw" in msg:
            render_answer(msg["raw"])
        else:
            st.markdown(msg["content"])

# 輸入框
if query := st.chat_input("輸入問題，例如：個人資料外洩後多久要通報？"):
    # 使用者訊息
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    # RAG 回答
    with st.chat_message("assistant"):
        with st.spinner("檢索中..."):
            try:
                result = generator.answer(query)
                data = result.model_dump()
                render_answer(data)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": data["answer"],
                    "raw": data,
                })
            except Exception as e:
                st.error(f"回答失敗：{e}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"錯誤：{e}",
                })
