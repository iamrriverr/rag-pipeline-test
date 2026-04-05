from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.models import Chunk, Section
from src.config import settings


def split_section_to_chunks(section: Section) -> list[Chunk]:
    content = section.content

    # 空 section（例如只有章標題沒有內文）不產生 chunk
    if not content.strip():
        return []

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
