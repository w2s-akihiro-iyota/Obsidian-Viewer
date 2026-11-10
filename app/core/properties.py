"""記事ページに出すプロパティ（frontmatter の項目）の表示用モデル（F-12）

frontmatter の値を、テンプレートがそのまま並べられる読み取り専用の形に直す。
HTML はここでは組み立てない（エスケープは Jinja の自動エスケープに任せる）。
文字列の中の [[...]] は、本文と同じ判定（classify_link）・同じ表示名と href（link_display）でリンクにする。
"""
from dataclasses import dataclass
from datetime import date, datetime

from app.core.note_resolver import NoteResolver
from app.services.wikilinks import MAX_FRONTMATTER_DEPTH, WikiLink, classify_link, link_display, split_wikilinks

# プロパティに出さない frontmatter のキー（title は見出し、tags はタグ、publish は公開状態として別に出ている）
HIDDEN_KEYS = frozenset({"title", "tags", "publish"})

_DATE_FORMAT = "%Y-%m-%d"
_DATETIME_FORMAT = "%Y-%m-%d %H:%M"


@dataclass(frozen=True)
class PropertyText:
    """文字列の中の、リンクでない部分"""
    text: str


@dataclass(frozen=True)
class PropertyLink:
    """文字列の中の [[...]] 1 つ分。href が None なら、存在しない先（本文と同じ internal-link-broken の表示）"""
    text: str
    href: str | None


# 1 つの値を表す部品の並び（文字とリンクが混ざる）
Fragments = tuple[PropertyText | PropertyLink, ...]


@dataclass(frozen=True)
class TextProperty:
    """1 つの値（文字列・数値・日付・はい/いいえ）"""
    key: str
    parts: Fragments


@dataclass(frozen=True)
class ChipsProperty:
    """リストの札。1 要素が 1 つの Fragments"""
    key: str
    chips: tuple[Fragments, ...]


@dataclass(frozen=True)
class NestedProperty:
    """辞書。1 段だけ (キー, 値) の組で出す"""
    key: str
    nested: tuple[tuple[str, Fragments], ...]


Property = TextProperty | ChipsProperty | NestedProperty

# 循環・深すぎる入れ子・同じ入れ物の 2 回目の代わりに出す文字
_ELLIPSIS = "…"


def _link_fragment(link: WikiLink, resolver: NoteResolver | None, source_path: str) -> PropertyText | PropertyLink:
    """[[...]] 1 つを、本文と同じ振り分け・表示名（link_display）で部品にする"""
    target = classify_link(link, None, resolver, source_path=source_path)
    display = link_display(link, target)
    return PropertyLink(display.text, display.href)


def _fragments(text: str, resolver: NoteResolver | None, source_path: str) -> Fragments:
    """文字列を、ただの文字とリンクの部品に分ける"""
    return tuple(
        _link_fragment(part, resolver, source_path) if isinstance(part, WikiLink) else PropertyText(part)
        for part in split_wikilinks(text)
    )


def _scalar_text(value) -> str:
    """文字列・数値・日付・はい/いいえ・None を表示する文字列にする（None は空）"""
    if value is None:
        return ""
    if isinstance(value, bool):      # bool は int の仲間なので先に見る
        return "はい" if value else "いいえ"
    if isinstance(value, datetime):  # datetime は date の仲間なので先に見る
        return value.strftime(_DATETIME_FORMAT)
    if isinstance(value, date):
        return value.strftime(_DATE_FORMAT)
    return str(value).strip()


def _flat_parts(value, seen: set[int], depth: int) -> list[str]:
    """
    入れ子の深いリスト・辞書を、空でない文字列の並びにする（「さらに深いものは文字列にする」）

    同じ入れ物（id）は 1 回しか見ず、深さも MAX_FRONTMATTER_DEPTH までにする（YAML のアンカーの循環・膨張対策）。
    見ない箇所は「…」にする。
    """
    if not isinstance(value, (dict, list, tuple)):
        text = _scalar_text(value)
        return [text] if text else []
    if id(value) in seen or depth > MAX_FRONTMATTER_DEPTH:
        return [_ELLIPSIS]
    seen.add(id(value))
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            inner = _flat_parts(v, seen, depth + 1)
            if inner:
                parts.append(f"{k}: {', '.join(inner)}")
        return parts
    return [t for v in value for t in _flat_parts(v, seen, depth + 1)]


def _value_fragments(value, resolver: NoteResolver | None, source_path: str, seen: set[int], depth: int) -> Fragments:
    """リストの要素・辞書の値 1 つの部品。文字列はリンクを分け、リストや辞書は文字列にする。空なら空のタプル"""
    if isinstance(value, str):
        return _fragments(value.strip(), resolver, source_path) if value.strip() else ()
    text = ", ".join(_flat_parts(value, seen, depth))
    return (PropertyText(text),) if text else ()


def _build_property(key: str, value, resolver: NoteResolver | None, source_path: str) -> Property | None:
    """項目 1 つを作る。値が空なら None（出さない）"""
    seen: set[int] = set()
    if isinstance(value, (dict, list, tuple)):
        seen.add(id(value))   # 自分自身を指す要素は「…」にする
    if isinstance(value, dict):
        nested = tuple(
            (str(k), frags) for k, v in value.items()
            if (frags := _value_fragments(v, resolver, source_path, seen, 1))
        )
        return NestedProperty(key, nested) if nested else None
    if isinstance(value, (list, tuple)):
        chips = tuple(frags for v in value if (frags := _value_fragments(v, resolver, source_path, seen, 1)))
        return ChipsProperty(key, chips) if chips else None
    parts = _value_fragments(value, resolver, source_path, seen, 0)
    return TextProperty(key, parts) if parts else None


def build_properties(frontmatter, source_path: str, resolver: NoteResolver | None = None) -> tuple[Property, ...]:
    """
    frontmatter から、記事ページに出すプロパティを書いてある順に作る

    HIDDEN_KEYS と、値が空の項目（None・空文字・空のリスト・空の辞書・空の要素しかないリスト）は出さない。
    リンク先は本文と同じ決め方（NoteResolver。リンク元は source_path のノート）。
    resolver を省略すると、いまのキャッシュの表を使う。
    """
    if not isinstance(frontmatter, dict):
        return ()
    props = (
        _build_property(str(key), value, resolver, source_path)
        for key, value in frontmatter.items() if str(key) not in HIDDEN_KEYS
    )
    return tuple(p for p in props if p is not None)
