from langchain_openai import OpenAIEmbeddings
from src.config import settings
from src.vectorstore.chroma_store import ChromaStore
from src.retriever.context import expand_context


class HybridRetriever:
    def __init__(self, store: ChromaStore):
        self._store = store
        self._embedder = OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.openai_api_key,
        )

    def retrieve(self, query: str, k: int = 5) -> list[dict]:
        # 向量檢索（OpenAI embedding 不需 query prefix）
        prefixed_query = settings.bge_query_prefix + query if settings.bge_query_prefix else query
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
