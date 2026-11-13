"""
タグを決める処理（X-1）

ノートのタグは、frontmatter の tags と、本文に書いた #タグ の両方から決める。
本文のタグは、描画（markdown.py の tag_plugin）でタグの札になるものだけを拾う。
正規表現で本文を直接探すと、コード・HTML・数式・参照式リンクの中まで拾い、描画と食い違うため、
描画と同じ解析（markdown-it）の結果から集める。タグの形・リンク先は tag_syntax.py にある。
"""
import re

from app.core.frontmatter import frontmatter_strings
from app.core.markdown import md, process_admonition_blocks
from app.services.wikilinks import WikiLink, split_wikilinks

# ふるい。# の後ろにタグの文字が続く所が 1 つも無い本文は、解析しないですぐ空を返す（全ノートの解析は重いため。Q-26）。
# 前の文字は問わない（>#tag・|#tag| も描画ではタグになる）。本当にタグかどうかは解析が決める
_SIEVE_RE = re.compile(r'#[\w\-/]')


def frontmatter_tags(frontmatter) -> list[str]:
    """
    frontmatter の tags をタグの一覧にする

    文字列なら 1 つ、リストなら各要素。数値（tags: 2024）も文字列にして受ける。
    先頭の # と前後の空白は外し、空は捨てる。frontmatter が dict でなくても空を返す。
    """
    raw = frontmatter.get('tags') if isinstance(frontmatter, dict) else None
    names = (name.lstrip('#').strip() for name in frontmatter_strings(raw))
    return list(dict.fromkeys(name for name in names if name))


def _mask_wikilinks(text: str) -> str:
    """
    [[...]] を空のリンク（<a></a>）に置き換える

    描画では process_wikilinks がリンクの <a>...</a> に変えるので、その文字の中（[[ノート #見出し]] の # など）はタグにならない。
    解析でも同じ結果にするため、リンクの形だけ残す。
    """
    return ''.join('<a></a>' if isinstance(part, WikiLink) else part for part in split_wikilinks(text))


def _tags_in_tokens(tokens) -> list[str]:
    """トークン（inline の children も）をたどり、タグの札（meta の tag）を出てきた順に返す。画像の代替文字の中は描画に出ないので見ない"""
    found = []
    for token in tokens:
        if token.type == 'image':
            continue
        name = (token.meta or {}).get('tag')
        if name:
            found.append(name)
        if token.children:
            found.extend(_tags_in_tokens(token.children))
    return found


def body_tags(body: str) -> list[str]:
    """本文に書いた #タグ のうち、描画でタグの札になるものを、出てくる順に返す（重複は 1 つ）"""
    if not _SIEVE_RE.search(body):
        return []
    # 描画（services/content.py の _render）と同じ前処理（process_admonition_blocks → [[...]] の置き換え）をして解析する
    tokens = md.parse(_mask_wikilinks(process_admonition_blocks(body)), {})
    return list(dict.fromkeys(_tags_in_tokens(tokens)))


def note_tags(frontmatter, body_tag_names) -> list[str]:
    """ノートのタグ。frontmatter のタグ → 本文のタグ（body_tags の結果）の順で、同じタグは最初に出た 1 つだけ"""
    return list(dict.fromkeys(frontmatter_tags(frontmatter) + list(body_tag_names)))
