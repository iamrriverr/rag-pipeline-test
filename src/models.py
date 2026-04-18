from enum import Enum
from pydantic import BaseModel, Field
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


# ===== Stage 1 V2 Models (new) =====

class BlockType(str, Enum):
    TITLE_PAGE_META = "TITLE_PAGE_META"
    TOC_HEADING = "TOC_HEADING"
    TOC_ENTRY = "TOC_ENTRY"
    REVISION_HISTORY_BLOCK = "REVISION_HISTORY_BLOCK"

    SECTION_HEADING = "SECTION_HEADING"
    CATEGORY_HEADING = "CATEGORY_HEADING"
    REGULATION_TITLE = "REGULATION_TITLE"
    ESTABLISHMENT_DATE = "ESTABLISHMENT_DATE"
    REVISION_DATE = "REVISION_DATE"

    CHAPTER_HEADING = "CHAPTER_HEADING"
    SUBSECTION_HEADING = "SUBSECTION_HEADING"
    ARTICLE = "ARTICLE"
    POINT = "POINT"

    PARAGRAPH = "PARAGRAPH"
    LIST_ITEM = "LIST_ITEM"
    TABLE = "TABLE"
    IMAGE = "IMAGE"

    UNKNOWN = "UNKNOWN"


class ExtractionMethod(str, Enum):
    PYTHON_DOCX_NATIVE = "PYTHON_DOCX_NATIVE"
    DOCLING = "DOCLING"
    VLM = "VLM"
    FALLBACK_TEXT = "FALLBACK_TEXT"


class TableRole(str, Enum):
    GENERIC = "GENERIC"
    PROCESS_DIAGRAM = "PROCESS_DIAGRAM"
    WORK_INSTRUCTION = "WORK_INSTRUCTION"
    NOTES = "NOTES"
    APPENDIX_FORM = "APPENDIX_FORM"


class BlockLocation(BaseModel):
    document_order_index: int

    virtual_document_title: str | None = None
    category: str | None = None
    section_breadcrumb: str | None = None

    preceding_text_snippet: str | None = None
    following_text_snippet: str | None = None

    compilation_page_reference: int | None = None

    source_paragraph_index: int | None = None
    source_table_index: int | None = None


class Block(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    block_type: BlockType
    content: str

    location: BlockLocation

    heading_level: int | None = None
    article_number: str | None = None
    point_number: str | None = None

    table_ref: int | None = None

    is_bold: bool = False
    is_italic: bool = False

    group_id: str | None = None
    task_id: str | None = None


class TableRecord(BaseModel):
    table_id: int

    raw_grid: list[list[str]]
    markdown: str
    html: str

    n_rows: int
    n_cols: int
    merged_cells: list[tuple[int, int, int, int]] = []

    location: BlockLocation

    extraction_method: ExtractionMethod
    extraction_confidence: float | None = None

    table_role: TableRole = TableRole.GENERIC

    group_id: str | None = None
    task_id: str | None = None

    serialized: dict | None = None


class ParseError(BaseModel):
    error_type: str
    message: str
    block_order_index: int | None = None
    severity: str = "WARNING"


class DocumentShape(str, Enum):
    COMPILATION = "COMPILATION"
    MANUAL_NARRATIVE = "MANUAL_NARRATIVE"
    MANUAL_SOP = "MANUAL_SOP"
    SINGLE_REGULATION = "SINGLE_REGULATION"
    OFFICIAL_DOC = "OFFICIAL_DOC"
    UNKNOWN = "UNKNOWN"


class ParsedDocument(BaseModel):
    source_path: str
    source_hash: str
    file_type: FileType
    detected_shape: DocumentShape = DocumentShape.UNKNOWN

    blocks: list[Block] = []
    tables: list[TableRecord] = []

    parse_errors: list[ParseError] = []
    source_metadata: dict = Field(default_factory=dict)


class VirtualDocument(BaseModel):
    id: UUID = Field(default_factory=uuid4)

    title: str
    category: str | None = None

    establishment_date_raw: str | None = None
    latest_revision_date_raw: str | None = None

    blocks: list[Block] = []
    tables: list[TableRecord] = []

    source_file_path: str
    source_file_hash: str
    source_order_in_compilation: int

    is_active: bool = True
    abolished_note: str | None = None
