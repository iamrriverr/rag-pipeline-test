import chromadb
from src.config import settings
from src.models import Chunk


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

    def clear(self) -> int:
        """清空整個 collection，回傳刪除的 chunk 數。"""
        deleted = self._collection.count()
        name = self._collection.name
        self._client.delete_collection(name=name)
        self._collection = self._client.get_or_create_collection(
            name=name, metadata={"hnsw:space": "cosine"}
        )
        return deleted

    @property
    def count(self) -> int:
        return self._collection.count()
