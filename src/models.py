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
