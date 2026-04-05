from langchain_openai import ChatOpenAI
from src.config import settings
from src.models import RAGResponse, Reference
from src.retriever.hybrid import HybridRetriever
from src.generator.prompts import RAG_SYSTEM_PROMPT, RAG_USER_TEMPLATE


class RAGGenerator:
    def __init__(self, retriever: HybridRetriever):
        self._retriever = retriever
        self._llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
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

        # 組裝 references（按 section 去重，保留分數最高者）
        seen_sections = set()
        references = []
        for r in results:
            sec_id = r["metadata"]["section_id"]
            if sec_id in seen_sections:
                continue
            seen_sections.add(sec_id)
            references.append(Reference(
                document_id=r["metadata"]["document_id"],
                document_title=r["metadata"]["document_title"],
                heading=r["metadata"]["heading"],
                breadcrumb=r["metadata"]["breadcrumb"],
                chunk_id=r["chunk_id"],
                content=r["content"][:200],
                relevance_score=round(1 - r["distance"], 3),
            ))

        # OpenAI text-embedding-3-small 的距離範圍較大，調整閾值
        confidence = "high" if results[0]["distance"] < 0.45 else \
                     "medium" if results[0]["distance"] < 0.65 else "low"

        return RAGResponse(
            answer=answer_text,
            references=references,
            confidence=confidence,
        )
