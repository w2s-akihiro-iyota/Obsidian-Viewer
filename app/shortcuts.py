"""キーボードショートカットの定義（F-9）

ヘルプのショートカット表・? のチートシート・ファイルツリーの下の段・エディタの下の段は、
すべてここの定義から描く。キーや説明を変えるときは、ここだけを直す。
実装（static/js/modules/ の search.js / file-tree.js / editor.js / shortcuts.js など）と食い違わないようにすること。

キーの持ち方:
    keys は「押し方」の並び。押し方は同時に押すキーの並び。
    (("Ctrl", "K"),)      → Ctrl+K
    (("↑",), ("↓",))      → ↑ ↓（どちらか）
説明文の [キー] は、表示のときにキーの見た目（kbd）で描く。

使える場所（contexts）:
    画面の id（PAGES）か、フォーカスの場所の id（FOCUS_PLACES）。
    フォーカスの場所は、テンプレートで要素に data-shortcut-place="<id>" として付け、
    JS（shortcuts.js の shortcutPlaceOf）はその目印だけで場所を判定する。
    下の段のヒントとチートシートは、フォーカスのある場所を contexts に持つグループを選ぶ・先頭に出す。

テンプレートからは、このモジュールを Jinja のグローバル shortcuts として使う（例: shortcuts.group("tree")）。
"""
import re
from dataclasses import dataclass

from markupsafe import Markup, escape

# 説明文の中で、キーの見た目で描く部分（例: 「先頭で [↑] を押すと」）
_INLINE_KEY_RE = re.compile(r"\[([^\[\]]+)\]")


@dataclass(frozen=True)
class Page:
    """画面の種類。チートシートで「いまの画面」に合わせてグループを並べるのに使う"""
    id: str
    label: str
    body_class: str     # templates の body に付くクラス（{% block body_class %}）


@dataclass(frozen=True)
class Shortcut:
    """1つのショートカット"""
    keys: tuple[tuple[str, ...], ...]
    description: str    # ヘルプの表に出す説明（[キー] はキーの見た目で描く）
    short: str          # チートシート・下の段に出す短い説明

    @property
    def description_html(self) -> Markup:
        """説明文の [キー] を <kbd> にした HTML（ほかの文字はエスケープする）"""
        parts = []
        last = 0
        for match in _INLINE_KEY_RE.finditer(self.description):
            parts.append(escape(self.description[last:match.start()]))
            parts.append(Markup("<kbd>{}</kbd>").format(match.group(1)))
            last = match.end()
        parts.append(escape(self.description[last:]))
        return Markup("").join(parts)


@dataclass(frozen=True)
class ShortcutGroup:
    """使える場所ごとのまとまり（ヘルプの表の見出し行・チートシートの節）"""
    id: str
    label: str
    shortcuts: tuple[Shortcut, ...]
    contexts: frozenset[str]    # 使える場所（画面の id か、フォーカスの場所の id）
    admin_only: bool = False


PAGES: tuple[Page, ...] = (
    Page("view", "記事ページ", "page-view"),
    Page("index", "ノート一覧", "page-index"),
    Page("graph", "グラフビュー", "graph-page"),
    Page("dashboard", "ダッシュボード", "dashboard-page"),
    Page("editor", "エディタ", "page-editor"),
)
ALL_PAGE_IDS = frozenset(page.id for page in PAGES)

# フォーカスの場所（data-shortcut-place の値）
FOCUS_QUICK_SWITCHER = "quick-switcher"
FOCUS_TREE_FILTER = "tree-filter"
FOCUS_TREE = "tree"
FOCUS_PLACES = frozenset({FOCUS_QUICK_SWITCHER, FOCUS_TREE_FILTER, FOCUS_TREE})

SHORTCUT_GROUPS: tuple[ShortcutGroup, ...] = (
    ShortcutGroup(
        id="global",
        label="どの画面でも",
        contexts=ALL_PAGE_IDS,
        shortcuts=(
            Shortcut((("Ctrl", "K"),), "クイックスイッチャーを開く・閉じる", "クイックスイッチャー"),
            Shortcut((("?",),), "ショートカット一覧を開く", "ショートカット一覧"),
            Shortcut((("Esc",),), "ヘルプ・ショートカット一覧・クイックスイッチャー・画像の拡大・つながりを閉じる", "閉じる"),
        ),
    ),
    ShortcutGroup(
        id="view",
        label="記事ページ",
        contexts=frozenset({"view"}),
        shortcuts=(
            Shortcut((("G",),), "つながりを開く・閉じる", "つながり"),
        ),
    ),
    ShortcutGroup(
        id="quick-switcher",
        label="クイックスイッチャー",
        contexts=frozenset({FOCUS_QUICK_SWITCHER}),
        shortcuts=(
            Shortcut((("↑",), ("↓",)), "候補を選ぶ", "選択"),
            Shortcut((("Enter",),), "開く", "開く"),
            Shortcut((("Ctrl", "Enter"),), "新しいタブで開く", "新しいタブ"),
        ),
    ),
    ShortcutGroup(
        id="tree-filter",
        label="ファイルツリーの絞り込み欄",
        contexts=frozenset({FOCUS_TREE_FILTER}),
        shortcuts=(
            Shortcut((("↓",),), "ツリーへ移る", "ツリーへ"),
            Shortcut((("Enter",),), "最初のノートを開く", "最初を開く"),
            Shortcut((("Esc",),), "絞り込みを消す", "消す"),
        ),
    ),
    ShortcutGroup(
        id="tree",
        label="ファイルツリー",
        contexts=frozenset({FOCUS_TREE}),
        shortcuts=(
            Shortcut((("↑",), ("↓",)), "上下に移る（先頭で [↑] を押すと絞り込み欄へ）", "移動"),
            Shortcut((("←",), ("→",)), "フォルダを閉じる・開く", "開閉"),
            Shortcut((("Home",), ("End",)), "先頭・末尾へ", "先頭・末尾"),
            Shortcut((("Enter",),), "ノートを開く・フォルダを開閉する", "開く"),
        ),
    ),
    ShortcutGroup(
        id="editor",
        label="エディタ（管理者のみ）",
        contexts=frozenset({"editor"}),
        admin_only=True,
        shortcuts=(
            Shortcut((("Ctrl", "S"),), "保存する", "保存"),
            Shortcut((("Tab",),), "字下げ（スペース4つ）", "字下げ"),
        ),
    ),
)

_GROUPS_BY_ID = {g.id: g for g in SHORTCUT_GROUPS}


def visible_groups(is_admin: bool) -> tuple[ShortcutGroup, ...]:
    """見せてよいグループを定義の順に返す（管理者でなければ管理者だけのグループを除く）"""
    return tuple(g for g in SHORTCUT_GROUPS if is_admin or not g.admin_only)


def group(group_id: str) -> ShortcutGroup:
    """id でグループを引く（無い id はテンプレートの書き間違いなので KeyError にする）"""
    return _GROUPS_BY_ID[group_id]


def find_shortcut(group_id: str, chord: tuple[str, ...]) -> Shortcut:
    """グループの中から、押し方 chord を含むショートカットを引く（無ければ KeyError）"""
    for shortcut in group(group_id).shortcuts:
        if chord in shortcut.keys:
            return shortcut
    raise KeyError((group_id, chord))


def find_page(body_class: str) -> Page | None:
    """body のクラスから画面の種類を引く（当てはまらなければ None）"""
    classes = set(str(body_class).split())
    return next((page for page in PAGES if page.body_class in classes), None)


def groups_for_page(page: Page | None, is_admin: bool) -> tuple[ShortcutGroup, ...]:
    """チートシートに出す順に並べたグループ

    その画面だけのグループ（エディタなど）→ どの画面でも使えるグループ → そのほか（定義の順）。
    画面が分からなければ定義の順のまま。
    """
    groups = visible_groups(is_admin)
    if page is None:
        return groups

    def rank(g: ShortcutGroup) -> int:
        if page.id not in g.contexts:
            return 2
        return 1 if g.contexts == ALL_PAGE_IDS else 0

    return tuple(sorted(groups, key=rank))   # sorted は安定なので、同じ順位の中は定義の順
