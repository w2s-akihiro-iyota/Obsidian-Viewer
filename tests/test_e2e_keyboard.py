"""キーボード操作の E2E（ブラウザで JS の動きを確かめる。Q-17。仕組みは conftest.py の e2e）

- Esc の優先順位: つながりが開いていれば、つながりだけ閉じる（ツリーの絞り込み欄の文字は残す）。
  ? の一覧などのモーダルが上に開いていれば、そちらに譲る（local-graph-panel.js・shortcuts.js）
- ツリーの絞り込み欄の Esc: 文字があれば消す。空なら何もしない（file-tree.js）
- G（つながり）: 記事ページで開く・閉じる。入力欄の中・Shift / Ctrl / Alt 付き・モーダルが開いている・変換中・押しっぱなしでは効かない
- ?（ショートカット一覧）: 開くと一覧へフォーカスを移し、閉じたら開く前の要素へ戻す。入力欄の中では開かない（shortcuts.js）
- Ctrl+K（クイックスイッチャー）: ↑↓ で選び、Enter で開く。止まったままのマウスで選び直さない（F-2）。Esc で閉じる（search.js）
- ツリー: 絞り込み欄で ↓ を押すと最初の項目、先頭で ↑ を押すと欄へ戻る（file-tree.js）
- 外部の人（公開用ポート）でも、Esc の優先順位と G は同じように動く
- 背景のスクロールの固定: モーダルが開いているあいだは、裏の本文をスクロールさせない（body.no-scroll。B-24）
- エディタ: Ctrl+S で保存し、ブラウザの保存は止める（保存の POST は page.route で受け、サーバーに届かせない）

直っていない不具合（ロードマップの ID）は、直したら通るテストを xfail(strict=True) で置いている（書き方の約束は
CLAUDE.md の Testing と conftest.py の E2ESite.precondition）。直して通るようになると XPASS で落ちるので、そのときは印を外す
"""
import re

import pytest

from conftest import (E2E_ACTIVE, E2E_ADMIN, E2E_GRAPH_BUTTON, E2E_GRAPH_PANEL, E2E_PUBLIC, E2E_SHORTCUT_SHEET,
                      E2E_VIEWERS, import_playwright)

playwright_api = import_playwright()
expect = playwright_api.expect
PlaywrightTimeoutError = playwright_api.TimeoutError

TREE_FILTER = "#file-tree-filter"
TREE_ITEMS = "#file-tree :is(.tree-folder, .tree-file)"
SHEET_FOCUS = f"{E2E_SHORTCUT_SHEET} .shortcut-sheet"
HELP = "#help-modal"
SEARCH = "#search-modal"
SEARCH_CONTENT = "#search-modal .search-modal-content"
SEARCH_INPUT = "#modal-search-input"
SEARCH_ITEMS = "#modal-search-results .search-result-item"
SETTINGS = "#settings-modal"
EDITOR_WRITES = re.compile(r"/api/editor/(save|update)$")

SELECTED = re.compile(r"\bselected\b")
NO_SCROLL = re.compile(r"\bno-scroll\b")


def _type_in_tree_filter(page, text):
    """ツリーの絞り込み欄にフォーカスを移して打つ（押すとパネルの外を押したことになって閉じるので、focus だけにする）"""
    page.locator(TREE_FILTER).focus()
    page.keyboard.type(text)


def _blur(page):
    page.evaluate("document.activeElement.blur()")


def _dispatch_g(page, **init):
    """G の keydown を JS で送る（変換中など、キーボードの操作では作れない状態を作る）"""
    page.evaluate("init => document.body.dispatchEvent(new KeyboardEvent('keydown', "
                  "{key: 'g', code: 'KeyG', bubbles: true, cancelable: true, ...init}))", init)


# ---------- Esc の優先順位 ----------

@pytest.mark.parametrize("viewer", E2E_VIEWERS)
def test_つながりを開いたままツリーの絞り込み欄でEscを押すとつながりだけ閉じて文字は残る(e2e, viewer):
    page = e2e.open(viewer=viewer)
    page.keyboard.press("g")
    expect(page.locator(E2E_GRAPH_PANEL)).to_be_visible()

    _type_in_tree_filter(page, "abc")
    page.keyboard.press("Escape")

    expect(page.locator(E2E_GRAPH_PANEL)).to_be_hidden()
    expect(page.locator(TREE_FILTER)).to_have_value("abc")
    expect(page.locator(E2E_GRAPH_BUTTON)).to_be_focused()


@pytest.mark.parametrize("viewer", E2E_VIEWERS)
def test_つながりの上に開いた一覧はEsc1回目で一覧だけ閉じ2回目でつながりを閉じる(e2e, viewer):
    page = e2e.open(viewer=viewer)
    page.keyboard.press("g")
    expect(page.locator(E2E_GRAPH_PANEL)).to_be_focused()
    page.keyboard.press("?")
    expect(page.locator(E2E_SHORTCUT_SHEET)).to_have_class(E2E_ACTIVE)

    page.keyboard.press("Escape")
    expect(page.locator(E2E_SHORTCUT_SHEET)).not_to_have_class(E2E_ACTIVE)
    expect(page.locator(E2E_GRAPH_PANEL)).to_be_visible()
    expect(page.locator(E2E_GRAPH_PANEL)).to_be_focused()

    page.keyboard.press("Escape")
    expect(page.locator(E2E_GRAPH_PANEL)).to_be_hidden()
    expect(page.locator(E2E_GRAPH_BUTTON)).to_be_focused()


def test_ツリーの絞り込み欄のEscは文字があれば消し空なら何もしない(e2e):
    page = e2e.open()
    expect(page.locator(TREE_ITEMS).first).to_be_visible()
    item_count = page.locator(TREE_ITEMS).count()

    _type_in_tree_filter(page, "abc")
    expect(page.locator("#file-tree .tree-empty")).to_be_visible()   # 一致するノートが無い
    page.keyboard.press("Escape")
    expect(page.locator(TREE_FILTER)).to_have_value("")
    expect(page.locator(TREE_ITEMS)).to_have_count(item_count)       # 絞り込みも解ける

    page.keyboard.press("Escape")
    expect(page.locator(TREE_FILTER)).to_have_value("")
    expect(page.locator(TREE_FILTER)).to_be_focused()
    expect(page.locator(TREE_ITEMS)).to_have_count(item_count)


# ---------- G（つながり） ----------

@pytest.mark.parametrize("viewer", E2E_VIEWERS)
def test_Gでつながりを開きもう一度押すと閉じる(e2e, viewer):
    page = e2e.open(viewer=viewer)
    button = page.locator(E2E_GRAPH_BUTTON)

    page.keyboard.press("g")
    expect(page.locator(E2E_GRAPH_PANEL)).to_be_visible()
    expect(page.locator(E2E_GRAPH_PANEL)).to_be_focused()
    expect(button).to_have_attribute("aria-expanded", "true")

    page.keyboard.press("g")
    expect(page.locator(E2E_GRAPH_PANEL)).to_be_hidden()
    expect(button).to_be_focused()
    expect(button).to_have_attribute("aria-expanded", "false")


def _g_in_input(page):
    _type_in_tree_filter(page, "g")
    expect(page.locator(TREE_FILTER)).to_have_value("g")    # 文字として入る


def _g_after_input(page):
    _blur(page)
    page.keyboard.press("g")


def _g_with_help_open(page):
    page.locator("#help-open-btn").click()
    expect(page.locator(HELP)).to_have_class(E2E_ACTIVE)
    page.keyboard.press("g")


def _g_after_help_closed(page):
    page.keyboard.press("Escape")
    expect(page.locator(HELP)).not_to_have_class(E2E_ACTIVE)
    page.keyboard.press("g")


# 効かない条件: (その条件で G を押す, その条件だけを外して G を押す)
G_BLOCKED = {
    "入力欄の中": (_g_in_input, _g_after_input),
    "Shift付き": (lambda page: page.keyboard.press("Shift+G"), lambda page: page.keyboard.press("g")),
    "Ctrl付き": (lambda page: page.keyboard.press("Control+g"), lambda page: page.keyboard.press("g")),
    "Alt付き": (lambda page: page.keyboard.press("Alt+g"), lambda page: page.keyboard.press("g")),
    "ヘルプが開いている": (_g_with_help_open, _g_after_help_closed),
    "変換中": (lambda page: _dispatch_g(page, isComposing=True), lambda page: _dispatch_g(page)),
}
# 外部の人は代表だけ流す（判定は管理者と同じ関数）
G_BLOCKED_CASES = [(E2E_ADMIN, name) for name in G_BLOCKED] + [(E2E_PUBLIC, "入力欄の中"), (E2E_PUBLIC, "ヘルプが開いている")]


@pytest.mark.parametrize(("viewer", "condition"), G_BLOCKED_CASES)
def test_Gは効かない条件では開かずその条件を外すと開く(e2e, viewer, condition):
    page = e2e.open(viewer=viewer)
    press_blocked, press_unblocked = G_BLOCKED[condition]

    press_blocked(page)
    expect(page.locator(E2E_GRAPH_PANEL)).to_be_hidden()

    press_unblocked(page)
    expect(page.locator(E2E_GRAPH_PANEL)).to_be_visible()


def test_Gを押しっぱなしにしても開閉を繰り返さない(e2e):
    page = e2e.open()
    page.keyboard.down("g")
    expect(page.locator(E2E_GRAPH_PANEL)).to_be_visible()
    # 離さずにもう一度 down すると、押しっぱなし（repeat: true）の keydown になる。1 回ずつ閉じていないことを見る
    for _ in range(2):
        page.keyboard.down("g")
        expect(page.locator(E2E_GRAPH_PANEL)).to_be_visible()
    page.keyboard.up("g")

    page.keyboard.press("g")
    expect(page.locator(E2E_GRAPH_PANEL)).to_be_hidden()


# ---------- ?（ショートカット一覧） ----------

def test_本文でクエスチョンを押すと一覧へフォーカスが移りEscで開く前の要素へ戻る(e2e):
    page = e2e.open()
    link = page.locator(".markdown-body a").first
    link.focus()

    page.keyboard.press("?")
    expect(page.locator(E2E_SHORTCUT_SHEET)).to_have_class(E2E_ACTIVE)
    expect(page.locator(SHEET_FOCUS)).to_be_focused()

    page.keyboard.press("Escape")
    expect(page.locator(E2E_SHORTCUT_SHEET)).not_to_have_class(E2E_ACTIVE)
    expect(link).to_be_focused()


def test_入力欄の中ではクエスチョンで一覧を開かない(e2e):
    page = e2e.open()
    _type_in_tree_filter(page, "?")
    expect(page.locator(TREE_FILTER)).to_have_value("?")
    expect(page.locator(E2E_SHORTCUT_SHEET)).not_to_have_class(E2E_ACTIVE)


# ---------- Ctrl+K（クイックスイッチャー） ----------

def test_クイックスイッチャーは矢印で選んだ候補を止まったままのマウスで選び直さずEnterで開く(e2e):
    page = e2e.open()
    page.keyboard.press("Control+k")
    expect(page.locator(SEARCH)).to_have_class(E2E_ACTIVE)
    expect(page.locator(SEARCH_INPUT)).to_be_focused()

    # 1 文字ずつ打つと、途中の語の結果で候補が描き直されることがあるので、1 回の入力で入れる
    page.locator(SEARCH_INPUT).fill(e2e.SEARCH_WORD)
    items = page.locator(SEARCH_ITEMS)
    expect(items.nth(2)).to_be_visible()
    expect(items.nth(0)).to_have_class(SELECTED)

    # マウスを 2 件目の上へ動かすと、2 件目を選ぶ
    box = items.nth(1).bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    expect(items.nth(1)).to_have_class(SELECTED)

    page.keyboard.press("ArrowDown")
    expect(items.nth(2)).to_have_class(SELECTED)

    # 表示が変わったときにブラウザが送る、止まったままのマウスの mousemove（F-2 の再発防止）。届いたことも確かめる
    page.evaluate("window.__e2eMoves = 0; document.getElementById('modal-search-results')"
                  ".addEventListener('mousemove', () => window.__e2eMoves++)")
    page.mouse.move(x, y)
    assert page.evaluate("window.__e2eMoves") > 0
    expect(items.nth(2)).to_have_class(SELECTED)
    expect(items.nth(1)).not_to_have_class(SELECTED)

    page.keyboard.press("ArrowUp")
    expect(items.nth(1)).to_have_class(SELECTED)
    page.keyboard.press("ArrowDown")
    expect(items.nth(2)).to_have_class(SELECTED)

    href = items.nth(2).evaluate("a => a.href")
    page.keyboard.press("Enter")
    page.wait_for_url(href)


def test_クイックスイッチャーはEscで閉じもう一度CtrlKで開ける(e2e):
    page = e2e.open()
    search, search_input = page.locator(SEARCH), page.locator(SEARCH_INPUT)
    page.keyboard.press("Control+k")
    expect(search).to_have_class(E2E_ACTIVE)
    search_input.fill(e2e.SEARCH_WORD)

    page.keyboard.press("Escape")
    expect(search).not_to_have_class(E2E_ACTIVE)

    page.keyboard.press("Control+k")
    expect(search).to_have_class(E2E_ACTIVE)
    expect(search_input).to_be_focused()
    expect(search_input).to_have_value("")      # 前に打った語は残さない


# ---------- ツリー ----------

def test_ツリーの絞り込み欄で下を押すと最初の項目へ移り先頭で上を押すと欄へ戻る(e2e):
    page = e2e.open()
    first = page.locator(TREE_ITEMS).first
    expect(first).to_be_visible()

    page.locator(TREE_FILTER).focus()
    page.keyboard.press("ArrowDown")
    expect(first).to_be_focused()

    page.keyboard.press("ArrowUp")
    expect(page.locator(TREE_FILTER)).to_be_focused()


# ---------- 背景のスクロールの固定（B-24） ----------

def _expect_wheel_does_not_scroll(page):
    """検索の枠の下（暗幕）でホイールを回しても、本文がスクロールしない（動き出すまで 2 フレーム待ってから見る）"""
    content = page.locator(SEARCH_CONTENT).bounding_box()
    viewport = page.viewport_size
    x = viewport["width"] / 2
    y = (content["y"] + content["height"] + viewport["height"]) / 2
    before = page.evaluate("document.scrollingElement.scrollTop")
    page.mouse.move(x, y)
    page.mouse.wheel(0, 600)
    page.evaluate("() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))")
    assert page.evaluate("document.scrollingElement.scrollTop") == before, "モーダルの裏で本文がスクロールした"


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="B-24: ? の一覧を開いたまま Ctrl+K を押すと、body の no-scroll が外れる（検索の裏で本文がスクロールする）")
def test_ショートカット一覧の上でCtrlKを押しても検索の裏で本文はスクロールしない(e2e):
    page = e2e.open()
    page.keyboard.press("?")
    with e2e.precondition():
        expect(page.locator(E2E_SHORTCUT_SHEET)).to_have_class(E2E_ACTIVE)
    page.keyboard.press("Control+k")
    with e2e.precondition():
        expect(page.locator(SEARCH)).to_have_class(E2E_ACTIVE)

    expect(page.locator("body")).to_have_class(NO_SCROLL)
    _expect_wheel_does_not_scroll(page)


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="B-24: 設定の上で Ctrl+K → Esc で検索を閉じると、設定は開いたままなのに body の no-scroll が外れる")
def test_設定の上で開いた検索をEscで閉じても設定は開いたままで背景は固定のまま(e2e):
    page = e2e.open()
    page.locator("#settings-open-btn").click()
    with e2e.precondition():
        expect(page.locator(SETTINGS)).to_have_class(E2E_ACTIVE)
    page.keyboard.press("Control+k")
    with e2e.precondition():
        expect(page.locator(SEARCH)).to_have_class(E2E_ACTIVE)
    page.keyboard.press("Escape")
    with e2e.precondition():
        expect(page.locator(SEARCH)).not_to_have_class(E2E_ACTIVE)

    expect(page.locator(SETTINGS)).to_have_class(E2E_ACTIVE)
    expect(page.locator("body")).to_have_class(NO_SCROLL)


# ---------- つながりの歩数のラジオ（B-25） ----------

@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="B-25: つながりの歩数（ラジオ）を押したあと、? で一覧が開かず G でつながりが閉じない（ラジオを文字の入力欄とみなす）")
def test_つながりの歩数を押したあともクエスチョンとGが効く(e2e):
    page = e2e.open()
    page.keyboard.press("g")
    with e2e.precondition():
        expect(page.locator(E2E_GRAPH_PANEL)).to_be_visible()
    page.locator("label[for='local-graph-depth-2']").click()
    with e2e.precondition():
        expect(page.locator("#local-graph-depth-2")).to_be_checked()

    # 歩数を押したまま（フォーカスはラジオ）で ? と G を押す
    page.keyboard.press("?")
    expect(page.locator(E2E_SHORTCUT_SHEET)).to_have_class(E2E_ACTIVE)
    page.keyboard.press("Escape")
    expect(page.locator(E2E_SHORTCUT_SHEET)).not_to_have_class(E2E_ACTIVE)

    page.keyboard.press("g")
    expect(page.locator(E2E_GRAPH_PANEL)).to_be_hidden()


# ---------- エディタの Ctrl+S（B-27） ----------

@pytest.mark.parametrize("key", [
    "s",
    # CapsLock 中は e.key が 'S' になる（Playwright では CapsLock の状態を作れないので、key が 'S' の Ctrl+S を送る）
    pytest.param("S", marks=pytest.mark.xfail(
        strict=True, raises=AssertionError,
        reason="B-27: e.key が 'S'（CapsLock 中）の Ctrl+S で、保存の POST が出ず、keydown も preventDefault されない")),
])
def test_エディタはCtrlSで保存しブラウザの保存を止める(e2e, key):
    page = e2e.open_path("/editor")
    saves = []

    def fake_save(route):
        # サーバーに届かせない（届くと本物の Vault に書きに行く）。偽の成功を返す
        saves.append(route.request.url)
        route.fulfill(json={"status": "success", "message": "保存しました（E2E の偽の応答）"})

    page.route(EDITOR_WRITES, fake_save)
    page.locator("#editor-filename").fill("e2e-保存の確かめ")
    page.locator("#editor-textarea").fill("本文")
    # document の keydown（editor.js）のあとに window で受け、保存の処理がブラウザの保存を止めたかを見る
    page.evaluate("window.__e2eSavePrevented = null; window.addEventListener('keydown', "
                  "e => { if (e.ctrlKey) window.__e2eSavePrevented = e.defaultPrevented; })")

    try:
        with page.expect_response(EDITOR_WRITES, timeout=e2e.wait_ms):
            page.keyboard.press(f"Control+{key}")
    except PlaywrightTimeoutError:
        raise AssertionError(f"Ctrl+{key} で保存の POST が出ない") from None
    assert len(saves) == 1
    assert page.evaluate("window.__e2eSavePrevented") is True
