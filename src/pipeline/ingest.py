from pathlib import Path
from uuid import uuid4
from src.config import settings
from src.models import Chunk, ChunkMetadata
from src.parsers.parser import DocumentParser
from src.cleaners.pipeline import clean_all
from src.splitters.section_splitter import split_by_heading
from src.splitters.chunk_splitter import split_section_to_chunks
from src.splitters.breadcrumb import build_breadcrumbs
from src.splitters.quality import check_quality
from src.vectorstore.chroma_store import ChromaStore
from langchain_openai import OpenAIEmbeddings
from tenacity import retry, wait_exponential, stop_after_attempt


class IngestPipeline:
    def __init__(self, parser: DocumentParser, store: ChromaStore):
        self._parser = parser
        self._store = store
        self._embedder = OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.openai_api_key,
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
        section_index_map: dict = {}
        for section in sections:
            chunks = split_section_to_chunks(section)
            section_index_map[section.id] = section.section_index
            for chunk in chunks:
                chunk.global_index = global_index
                global_index += 1
            all_chunks.extend(chunks)
            section.char_count = sum(c.char_count for c in chunks)

        # 設定 document_id
        for chunk in all_chunks:
            chunk.document_id = document_id

        # 品質檢查
        issues = check_quality(all_chunks)

        # Stage 4: Embedding
        contents = [c.content for c in all_chunks]
        vectors = self._embed_batch(contents)

        # Stage 4: 寫入 Chroma
        metadatas = [
            self._build_metadata(c, document_id, title, department,
                                 section_index_map.get(c.section_id, 0))
            for c in all_chunks
        ]
        self._store.add_chunks(all_chunks, vectors, metadatas)

        return {
            "document_id": document_id,
            "title": title,
            "file_type": file_type.value,
            "section_count": len(sections),
            "chunk_count": len(all_chunks),
            "quality_issues": len(issues),
            "sections": [
                {"heading": s.heading, "chunk_count": len(split_section_to_chunks(s))}
                for s in sections
            ],
        }

    @retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.embed_documents(texts)

    def _build_metadata(self, chunk: Chunk, doc_id: str,
                        title: str, department: str, section_index: int) -> dict:
        return ChunkMetadata(
            document_id=doc_id,
            document_title=title,
            department=department,
            section_id=str(chunk.section_id),
            section_index=section_index,
            heading=chunk.heading,
            heading_level=chunk.heading_level,
            breadcrumb=chunk.breadcrumb,
            content_type=chunk.content_type.value,
            chunk_index=chunk.chunk_index,
            global_index=chunk.global_index,
            total_chunks_in_section=chunk.total_chunks_in_section,
            embedding_model=settings.embedding_model,
        ).model_dump()
