from pathlib import Path
from docling.document_converter import DocumentConverter
from docling.datamodel.document import TableItem, PictureItem
import fitz
from src.models import ContentType
from src.vlm.client import VLMClient


class DoclingParser:
    """Docling 版面分析 + VLM 三通道。"""

    def __init__(self, vlm_client: VLMClient | None = None):
        self._converter = DocumentConverter()
        self._vlm = vlm_client

    def parse(self, file_path: Path) -> list[dict]:
        """回傳 [{content, content_type, page_no, vlm_confidence}, ...]"""
        result = self._converter.convert(str(file_path))
        doc = result.document
        pdf_doc = fitz.open(str(file_path)) if file_path.suffix.lower() == '.pdf' else None

        parts = []
        for item, _level in doc.iterate_items():
            if isinstance(item, TableItem) and self._vlm and pdf_doc:
                page_no = item.prov[0].page_no if item.prov else 0
                page_img = self._rasterize_page(pdf_doc, page_no)
                if not page_img:
                    continue
                text = self._vlm.table_to_text(page_img)
                parts.append({
                    "content": text,
                    "content_type": ContentType.VLM_TABLE,
                    "page_no": page_no,
                    "vlm_confidence": 0.9,
                })

            elif isinstance(item, PictureItem) and self._vlm and pdf_doc:
                page_no = item.prov[0].page_no if item.prov else 0
                page_img = self._rasterize_page(pdf_doc, page_no)
                if not page_img:
                    continue
                text = self._vlm.image_to_text(page_img)
                parts.append({
                    "content": text,
                    "content_type": ContentType.VLM_IMAGE,
                    "page_no": page_no,
                    "vlm_confidence": 0.85,
                })

            else:
                if hasattr(item, 'text') and item.text:
                    page_no = item.prov[0].page_no if hasattr(item, 'prov') and item.prov else 0
                    parts.append({
                        "content": item.text,
                        "content_type": ContentType.TEXT,
                        "page_no": page_no,
                        "vlm_confidence": None,
                    })

        if pdf_doc:
            pdf_doc.close()
        return parts

    def _rasterize_page(self, pdf_doc, page_no: int, dpi: int = 200) -> bytes:
        """將 PDF 頁面轉為 PNG bytes。Docling 的 page_no 是 1-indexed。"""
        if not pdf_doc:
            return b""
        # Docling 1-indexed → PyMuPDF 0-indexed；超出範圍則夾在有效區間內
        idx = max(0, min(page_no - 1, len(pdf_doc) - 1))
        page = pdf_doc[idx]
        pix = page.get_pixmap(dpi=dpi)
        return pix.tobytes("png")
