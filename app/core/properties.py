"""記事ページに出すプロパティ（frontmatter の項目）の表示用モデル（F-12）

frontmatter の値を、テンプレートがそのまま並べられる読み取り専用の形に直す。
HTML はここでは組み立てない（エスケープは Jinja の自動エスケープに任せる）。
文字列の中の [[...]] は、本文と同じ判定（classify_link）・同じ href（note_href）でリンクにする。
"""
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum, auto

from app.core.note_resolver import NoteResolver
from app.services.wikilinks import LinkKind, WikiLink, classify_link, note_href, split_wikilinks
from app.core.markdown import heading_anchor

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


class PropertyKind(Enum):
    """値の見せ方"""
    TEXT = auto()     # 1 つの値（文字列・数値・日付・はい/いいえ）
    CHIPS = auto()    # リストの札
    NESTED = auto()   # 辞書（キーと値を 2 列で）


@dataclass(frozen=True)
class Property:
    """プロパティ 1 項目。kind に応じて parts / chips / nested のどれか 1 つだけが入る"""
    key: str
    kind: PropertyKind
    parts: Fragments = ()
    chips: tuple[Fragments, ...] = ()
    nested: tuple[tuple[str, Fragments], ...] = ()


def _link_fragment(link: WikiLink, resolver: NoteResolver | None, source_path: str) -> PropertyText | PropertyLink:
    """[[...]] 1 つを、描画（process_wikilinks）と同じ振り分けでリンク・リンク切れ・見出しリンクにする"""
    name, heading = link.name, link.heading
    target = classify_link(link, None, resolver, source_path=source_path)
    if target.kind is LinkKind.IMAGE:
        return PropertyLink(name, target.image_url)
    if target.kind is LinkKind.HEADING:
        return PropertyLink(link.alias or heading, f"#{heading_anchor(heading)}")
    title = link.alias or (f"{name} > {heading}" if heading else name)
    if target.kind is not LinkKind.NOTE:   # 存在しないノート・見つからない画像
        return PropertyLink(title, None)
    return PropertyLink(title, note_href(target.path, heading))


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


def _flat_text(value) -> str:
    """入れ子の深いリスト・辞書を 1 つの文字列にする（「さらに深いものは文字列にする」）"""
    if isinstance(value, dict):
        pairs = (f"{k}: {_flat_text(v)}" for k, v in value.items())
        return ", ".join(p for p in pairs if not p.endswith(": "))
    if isinstance(value, (list, tuple)):
        return ", ".join(t for t in (_flat_text(v) for v in value) if t)
    return _scalar_text(value)


def _value_fragments(value, resolver: NoteResolver | None, source_path: str) -> Fragments:
    """リストの要素・辞書の値 1 つの部品。文字列はリンクを分け、リストや辞書は文字列にする。空なら空のタプル"""
    if isinstance(value, str):
        return _fragments(value.strip(), resolver, source_path) if value.strip() else ()
    text = _flat_text(value)
    return (PropertyText(text),) if text else ()


def _build_property(key: str, value, resolver: NoteResolver | None, source_path: str) -> Property | None:
    """項目 1 つを作る。値が空なら None（出さない）"""
    if isinstance(value, dict):
        nested = tuple(
            (str(k), frags) for k, v in value.items()
            if (frags := _value_fragments(v, resolver, source_path))
        )
        return Property(key, PropertyKind.NESTED, nested=nested) if nested else None
    if isinstance(value, (list, tuple)):
        chips = tuple(frags for v in value if (frags := _value_fragments(v, resolver, source_path)))
        return Property(key, PropertyKind.CHIPS, chips=chips) if chips else None
    parts = _value_fragments(value, resolver, source_path)
    return Property(key, PropertyKind.TEXT, parts=parts) if parts else None


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
