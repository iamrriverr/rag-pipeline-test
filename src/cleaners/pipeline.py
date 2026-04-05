import re
import hashlib
from collections import Counter


def fix_cjk_spacing(text: str) -> str:
    return re.sub(r'([\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', r'\1', text)


def remove_repeated_headers(text: str, threshold: int = 3) -> str:
    lines = text.split('\n')
    counts = Counter(line.strip() for line in lines if line.strip())
    repeated = {line for line, c in counts.items() if c >= threshold and len(line) < 50}
    return '\n'.join(line for line in lines if line.strip() not in repeated)


_REG_SUFFIXES = r'(?:辦法|要點|規範|注意事項|作業程序|處理方法|計畫|準則|規則)'
_REG_PREFIXES = r'(?:汐止區農會|本會)'


def detect_legal_structure(text: str) -> str:
    # 1. 法規標題若黏在其他內容末尾，先斷行分開
    text = re.sub(
        rf'(?<!\n)({_REG_PREFIXES}[^\n]*?{_REG_SUFFIXES})(?=\s|$)',
        r'\n\1', text
    )
    # 2. 章標題後若直接黏著條文（同一行），先斷行分開
    text = re.sub(
        r'(第[一二三四五六七八九十百]+章\s*[^\n第]*?)(第[一二三四五六七八九十百]+條)',
        r'\1\n\2', text
    )
    # 3. 法規標題 → H1（整行必須以法規後綴結尾，長度 8-60）
    text = re.sub(
        rf'^({_REG_PREFIXES}[^\n]{{4,56}}{_REG_SUFFIXES})\s*$',
        r'# \1', text, flags=re.MULTILINE
    )
    # 4. 章 → H2
    text = re.sub(r'^(第[一二三四五六七八九十百]+章)\s*(.+)$',
                  r'## \1 \2', text, flags=re.MULTILINE)
    # 5. 條 → H3
    text = re.sub(r'^(第[一二三四五六七八九十百]+條)\s*',
                  r'### \1 ', text, flags=re.MULTILINE)
    return text


def mask_pii(text: str) -> str:
    text = re.sub(r'([A-Z])\d{5}(\d{4})', r'\1*****\2', text)
    text = re.sub(r'(09\d{2})\d{3}(\d{3})', r'\1***\2', text)
    return text


def compute_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def clean_all(text: str) -> str:
    text = fix_cjk_spacing(text)
    text = remove_repeated_headers(text)
    text = detect_legal_structure(text)
    text = mask_pii(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
