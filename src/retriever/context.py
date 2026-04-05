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
