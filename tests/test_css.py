"""CSS の約束のテスト（Q-33）

- モーダルの重なり（z-index）は、variables.css の --z-* から決める（数字を直書きしない）。
  core.js の MODALS_TOP_FIRST の並びの根拠を、変数だけで追えるようにするため。
  並びと実際の重なりが合っているかは、test_e2e_keyboard.py の test_モーダルの一覧の順は実際の重なりの順と合う が見る
"""
import re

import pytest

from app.config import STATICS_DIR

CSS_MODULES = STATICS_DIR / "css" / "modules"

# モーダルとその部品の z-index を決めているルール（ファイル, セレクタ）
MODAL_LAYER_RULES = [
    ("tutorial.css", "#welcome-modal.settings-modal"),
    ("tutorial.css", "#help-modal.settings-modal"),
    ("settings.css", ".settings-modal"),
    ("settings.css", ".search-modal"),
    ("content.css", ".lightbox-overlay"),
    ("content.css", ".lightbox-close"),
]


def _z_index(file: str, selector: str) -> str:
    """そのセレクタだけのルールのうち、z-index を持つ最後のもの（後ろが勝つ）の値"""
    text = re.sub(r"/\*.*?\*/", "", (CSS_MODULES / file).read_text(encoding="utf-8"), flags=re.S)
    rules = re.findall(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", text)
    assert rules, f"{file} に {selector} のルールが無い"
    values = [m.group(1).strip() for body in rules if (m := re.search(r"z-index\s*:\s*([^;]+);", body))]
    assert values, f"{file} の {selector} に z-index が無い"
    return values[-1]


@pytest.mark.parametrize("file, selector", MODAL_LAYER_RULES)
def test_モーダルの重なりはvariables_cssの変数から決める(file, selector):
    value = _z_index(file, selector)
    assert re.fullmatch(r"(var|calc)\(.*--z-[a-z-]+.*\)", value), f"{file} の {selector} の z-index が数字の直書き: {value}"
