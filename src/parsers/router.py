from pathlib import Path
from src.models import FileType

MIME_MAP = {
    ".pdf": FileType.PDF,
    ".docx": FileType.DOCX, ".doc": FileType.DOCX,
    ".md": FileType.MARKDOWN, ".mdx": FileType.MARKDOWN,
    ".txt": FileType.TXT, ".log": FileType.TXT,
    ".csv": FileType.CSV, ".tsv": FileType.CSV,
    ".xlsx": FileType.XLSX, ".xls": FileType.XLSX,
    ".rar": FileType.ARCHIVE, ".zip": FileType.ARCHIVE,
}


def detect_file_type(filename: str) -> FileType:
    suffix = Path(filename).suffix.lower()
    return MIME_MAP.get(suffix, FileType.UNSUPPORTED)
