"""
本文のタグ（#タグ）の「形」とリンク先（X-1）

描画（markdown.py の tag_plugin）も、索引・記事ページのタグ集め（tags.py の body_tags）も、
タグの形・数字だけを除く判定・リンク先はここだけを読む（どちらも markdown.py / tags.py から読まれる葉のモジュール）。

本文のタグの規則は Obsidian に合わせる。
- # の前が行頭か空白
- 続く文字は文字・数字・_・-・/（全角の句読点や括弧はタグに含めず、そこで切れる）
- 数字だけ（#18・#2024）はタグにしない
- 末尾の / は外す
"""
import re
from urllib.parse import quote

# 本文のタグの形。(?<!\S) は「前が行頭か空白」。\w は日本語の文字も含むが、。】）などの記号は含まない
TAG_RE = re.compile(r'(?<!\S)#([\w\-/]+)')


def tag_name_from_match(match: re.Match) -> str | None:
    """TAG_RE に当たった結果から、タグの名前を返す。タグにしないもの（数字だけ・/ だけ）は None"""
    name = match.group(1).rstrip('/')
    if not name or name.replace('/', '').isdigit():
        return None
    return name


def tag_href(name: str) -> str:
    """タグでノート一覧を絞り込む URL（& # ? % + 空白も壊れないよう、/ 以外をエンコードする）"""
    return f"/?tag={quote(name, safe='/')}"
