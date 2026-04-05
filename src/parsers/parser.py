from pathlib import Path
from src.models import FileType
from src.parsers.router import detect_file_type
from src.parsers.docling_parser import DoclingParser
from src.vlm.client import VLMClient
from src.splitters.metadata import extract_inline_metadata
import pandas as pd
import re


class DocumentParser:
    def __init__(self, vlm_client: VLMClient | None = None):
        self._docling = DoclingParser(vlm_client)

    def parse(self, file_path: Path) -> tuple[str, FileType, dict]:
        """回傳 (markdown, file_type, inline_metadata)"""
        file_type = detect_file_type(file_path.name)

        match file_type:
            case FileType.PDF | FileType.DOCX:
                parts = self._docling.parse(file_path)
                md = "\n\n".join(p["content"] for p in parts if p["content"])
            case FileType.MARKDOWN:
                md = file_path.read_text(encoding="utf-8")
            case FileType.TXT:
                md = self._parse_txt(file_path)
            case FileType.CSV:
                md = self._parse_csv(file_path)
            case FileType.XLSX:
                md = self._parse_xlsx(file_path)
            case _:
                raise ValueError(f"不支援: {file_path.suffix}")

        inline_meta, md = extract_inline_metadata(md)
        return md, file_type, inline_meta

    def _parse_txt(self, path: Path) -> str:
        raw = path.read_text(encoding="utf-8")
        raw = re.sub(r'^(第[一二三四五六七八九十百]+章)\s*(.+)$',
                     r'# \1 \2', raw, flags=re.MULTILINE)
        raw = re.sub(r'^(第[一二三四五六七八九十百]+條)\s*',
                     r'## \1 ', raw, flags=re.MULTILINE)
        return raw

    def _parse_csv(self, path: Path) -> str:
        df = pd.read_csv(path)
        return f"## {path.stem}\n\n{df.to_markdown(index=False)}"

    def _parse_xlsx(self, path: Path) -> str:
        sheets = pd.read_excel(path, sheet_name=None)
        parts = []
        for name, df in sheets.items():
            parts.append(f"## {name}\n\n{df.to_markdown(index=False)}")
        return "\n\n".join(parts)
