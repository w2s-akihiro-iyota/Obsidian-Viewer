"""ノートの frontmatter（先頭の --- で囲んだ YAML）を読む（Q-13）

索引作り（indexing）とリンクの描画（wikilinks）の両方が使う。前は indexing にあり、wikilinks が indexing を読み込むので、
indexing からは wikilinks を関数の中で読み込んで循環を避けていた。どちらも読み込むだけの小さなモジュールに分けた
"""
import re
from dataclasses import dataclass

import yaml


@dataclass(frozen=True)
class FrontmatterResult:
    """frontmatter を読んだ結果。error は読めたなら空文字、読めなかったときはその理由（F-14）"""
    data: dict
    body: str
    error: str = ""


# 開きの行。空行を除いた最初の行が --- だけ（後ろの空白は可）。---------- や --- メモ --- のような区切り線で始まる本文は frontmatter ではない（F-14）
_OPEN_RE = re.compile(r'(?:[ \t]*\n)*[ \t]*---[ \t]*(?:\n|$)')
# 先頭の --- ... ---。中身が空（開きの直後に閉じ）でも合う
_FRONTMATTER_RE = re.compile(r'^\s*---\s*\n(?:(.*?)\n)??---(?:\s*\n|$)', re.DOTALL)


def read_frontmatter(content: str) -> FrontmatterResult:
    """
    先頭の frontmatter を読む（先頭の BOM は外し、改行は LF にそろえる）

    - 無い: data は {}、本文は元のまま、error は空
    - 読めた: data は辞書、本文は閉じの --- の後ろ。中身が空・None でも error は空
    - 読めない: data は {}、error に理由を入れる。本文は、YAML の誤り・閉じが無いときは元のまま、
      辞書でないとき（key: value の形でない）は閉じの後ろ
    """
    if content.startswith('\ufeff'):
        content = content[1:]
    normalized = content.replace('\r\n', '\n')

    if not _OPEN_RE.match(normalized):
        return FrontmatterResult({}, content)
    match = _FRONTMATTER_RE.match(normalized)
    if not match:
        # 中身が区切り線 1 本だけのノートは frontmatter ではない（閉じが無いと警告しない）
        if normalized.strip() == '---':
            return FrontmatterResult({}, content)
        return FrontmatterResult({}, content, "閉じの --- が無い")

    body = normalized[match.end():]
    try:
        data = yaml.safe_load(match.group(1) or "")
    except Exception as e:
        return FrontmatterResult({}, content, _yaml_error(e, normalized, match))
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return FrontmatterResult({}, body, "key: value の形になっていない")
    return FrontmatterResult(data, body)


def _yaml_error(error: Exception, text: str, match: re.Match) -> str:
    """YAML の例外の理由。行番号はファイル全体での値（YAML の手前の行数を足す）"""
    mark = getattr(error, "problem_mark", None)
    if mark is None or match.start(1) < 0:
        return "YAML の書き方の誤り"
    lines_before_yaml = text.count('\n', 0, match.start(1))
    return f"YAML の書き方の誤り（{lines_before_yaml + mark.line + 1} 行目）"


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """先頭の frontmatter を読み、(frontmatter の辞書, 本文) を返す。無い・読めないときは辞書が {}
    （理由が要るときは read_frontmatter）"""
    result = read_frontmatter(content)
    return result.data, result.body


def frontmatter_strings(value) -> list[str]:
    """
    frontmatter の値を文字列のリストにする（X-1・X-2。aliases・tags の共通の正規化）

    None は空、単独の値は 1 要素、リストは各要素。数値も文字列にし、前後の空白を外して空は捨て、重複は 1 つにする。
    入れ子の値（辞書・リストの要素）は文字列にできないので捨てる。
    """
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    names = (str(item).strip() for item in items if item is not None and not isinstance(item, (dict, list, tuple)))
    return list(dict.fromkeys(name for name in names if name))


def note_aliases(frontmatter: dict) -> list[str]:
    """frontmatter の aliases（別名）の一覧（X-2）"""
    return frontmatter_strings(frontmatter.get("aliases"))


def is_published(frontmatter: dict) -> bool:
    """frontmatterのpublishフィールドがTrueかどうかを判定します。"""
    publish_state = frontmatter.get('publish')
    return publish_state is True or str(publish_state).lower() == 'true'
