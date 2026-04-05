from src.cleaners.pipeline import (
    fix_cjk_spacing,
    detect_legal_structure,
    mask_pii,
    clean_all,
)


def test_fix_cjk_spacing():
    assert fix_cjk_spacing("開 戶 作 業") == "開戶作業"


def test_detect_legal_structure():
    text = "第一章 總則\n第一條 本辦法依..."
    out = detect_legal_structure(text)
    assert out.startswith("## 第一章 總則")
    assert "### 第一條 " in out


def test_detect_regulation_title():
    text = "前言\n汐止區農會信用部個人資料檔案安全維護管理辦法\n第一章 總則\n第一條 依本法..."
    out = detect_legal_structure(text)
    assert "# 汐止區農會信用部個人資料檔案安全維護管理辦法" in out
    assert "## 第一章 總則" in out
    assert "### 第一條 " in out


def test_mask_pii():
    assert mask_pii("A123456789") == "A*****6789"
    assert mask_pii("0912345678") == "0912***678"


def test_clean_all():
    raw = "開 戶 第一章 總則\n\n\n\n內容"
    out = clean_all(raw)
    assert "開戶" in out
    assert "\n\n\n" not in out
