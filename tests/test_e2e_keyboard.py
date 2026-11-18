"""キーボード操作の E2E（ブラウザで JS の動きを確かめる。Q-17。仕組みは conftest.py の e2e）

- Esc の優先順位: つながりが開いていれば、つながりだけ閉じる（ツリーの絞り込み欄の文字は残す）。
  ? の一覧などのモーダルが上に開いていれば、そちらに譲る（local-graph-panel.js・shortcuts.js）
- ツリーの絞り込み欄の Esc: 文字があれば消す。空なら何もしない（file-tree.js）
- G（つながり）: 記事ページで開く・閉じる。入力欄の中・Shift / Ctrl / Alt 付き・モーダルが開いている・変換中・押しっぱなしでは効かない
- ?（ショートカット一覧）: 開くと一覧へフォーカスを移し、閉じたら開く前の要素へ戻す。入力欄の中では開かない（shortcuts.js）
- Ctrl+K（クイックスイッチャー）: ↑↓ で選び、Enter で開く。止まったままのマウスで選び直さない（F-2）。Esc で閉じる（search.js）
- ツリー: 絞り込み欄で ↓ を押すと最初の項目、先頭で ↑ を押すと欄へ戻る（file-tree.js）
- 外部の人（公開用ポート）でも、Esc の優先順位と G は同じように動く
- モーダルの重なり: ヘルプ・設定・ようこその上で開いた検索は、見た目でもいちばん上に出る（B-29）。
  重なっていたら、1 回の Esc でいちばん上の 1 つだけ閉じる（その検索、設定の中のフォルダ選び。B-28）。
  設定も Esc で閉じ、チュートリアル中ならチュートリアルも終える（X-9）
- 背景のスクロールの固定: モーダル（画像の拡大も。X-11）が開いているあいだは、裏の本文をスクロールさせない（body.no-scroll。B-24）
- エディタ: Ctrl+S で保存し、ブラウザの保存は止める（保存の POST は page.route で受け、サーバーに届かせない）

直っていない不具合（ロードマップの ID）は、直したら通るテストを xfail(strict=True) で置く（書き方の約束は
CLAUDE.md の Testing と conftest.py の E2ESite.precondition）。直して通るようになると XPASS で落ちるので、そのときは印を外す
"""
import re

import pytest

from conftest import (E2E_ACTIVE, E2E_ADMIN, E2E_DIR_BROWSER, E2E_FAKE_SYNC_CONFIG, E2E_GRAPH_BUTTON, E2E_GRAPH_PANEL,
                      E2E_IMAGE_NOTE, E2E_PUBLIC, E2E_SHORTCUT_SHEET, E2E_VIEWERS, import_playwright)

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
WELCOME = "#welcome-modal"
TUTORIAL_BANNER = "#tutorial-banner"
LIGHTBOX = "#lightbox-overlay"
LIGHTBOX_IMAGE = "#lightbox-image"
EDITOR_WRITES = re.compile(r"/api/editor/(save|update)$")

SELECTED = re.compile(r"\bselected\b")
NO_SCROLL = re.compile(r"\bno-scroll\b")
# 開いている（.active）。ようこそは閉じるとき .closing を付け、消え終わってから .active を外すので、.closing が付いたら閉じたとみなす
OPEN = re.compile(r"^(?!.*\bclosing\b).*\bactive\b")


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


# ---------- モーダルの重なりと Esc（B-28・X-9） ----------

def _open_help(e2e):
    page = e2e.open()
    page.locator("#help-open-btn").click()
    return page


def _open_settings(e2e):
    page = e2e.open()
    page.locator("#settings-open-btn").click()
    return page


def _open_welcome(e2e):
    return e2e.open(welcome=True)   # 画面に出た 1 秒後に出る


# 検索の下に置くモーダル: (セレクタ, そのモーダルを開いたページを返す)
UNDER_SEARCH = {
    "ヘルプ": (HELP, _open_help),
    "設定": (SETTINGS, _open_settings),
    "ようこそ": (WELCOME, _open_welcome),
}

# 検索の入力欄の真ん中に描かれているもの（いちばん上の要素）が、検索の中か
SEARCH_INPUT_DRAWN_ON_TOP = """() => {
    const box = document.querySelector('#modal-search-input').getBoundingClientRect();
    const drawn = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
    return Boolean(drawn && drawn.closest('#search-modal'));
}"""


@pytest.mark.parametrize("under", UNDER_SEARCH)
def test_ヘルプや設定やようこその上で開いた検索は見た目でもいちばん上に出る(e2e, under):
    selector, open_under = UNDER_SEARCH[under]
    page = open_under(e2e)
    with e2e.precondition():
        expect(page.locator(selector)).to_have_class(OPEN)
    page.keyboard.press("Control+k")
    with e2e.precondition():
        expect(page.locator(SEARCH)).to_have_class(E2E_ACTIVE)

    e2e.wait_until(page, SEARCH_INPUT_DRAWN_ON_TOP, f"{under}の上で開いた検索が、{under}の下に隠れている（B-29）")


@pytest.mark.parametrize("under", UNDER_SEARCH)
def test_ヘルプや設定やようこその上で開いた検索はEsc1回目で検索だけ閉じ2回目で下のモーダルを閉じる(e2e, under):
    selector, open_under = UNDER_SEARCH[under]
    page = open_under(e2e)
    modal, search, body = page.locator(selector), page.locator(SEARCH), page.locator("body")
    with e2e.precondition():
        expect(modal).to_have_class(OPEN)
    page.keyboard.press("Control+k")
    with e2e.precondition():
        expect(search).to_have_class(E2E_ACTIVE)

    page.keyboard.press("Escape")
    expect(search).not_to_have_class(E2E_ACTIVE)
    expect(modal).to_have_class(OPEN)
    expect(body).to_have_class(NO_SCROLL)

    page.keyboard.press("Escape")
    expect(modal).not_to_have_class(OPEN)
    expect(body).not_to_have_class(NO_SCROLL)


def test_ようこそが出ているあいだはツリーの絞り込み欄でEscを押してもようこそだけ閉じて文字は残る(e2e):
    # ようこそはフォーカスを奪わないので、打っている最中に出ると、フォーカスは絞り込み欄に残る
    page = e2e.open(welcome=True)
    _type_in_tree_filter(page, "abc")
    with e2e.precondition():
        expect(page.locator(WELCOME)).to_have_class(OPEN)
        expect(page.locator(TREE_FILTER)).to_be_focused()

    page.keyboard.press("Escape")
    expect(page.locator(WELCOME)).not_to_have_class(OPEN)
    expect(page.locator(TREE_FILTER)).to_have_value("abc")


@pytest.mark.parametrize("viewer", E2E_VIEWERS)
def test_設定はEscで閉じ背景の固定も外れる(e2e, viewer):
    page = e2e.open(viewer=viewer)
    settings, body = page.locator(SETTINGS), page.locator("body")
    page.locator("#settings-open-btn").click()
    with e2e.precondition():
        expect(settings).to_have_class(E2E_ACTIVE)
        expect(body).to_have_class(NO_SCROLL)

    page.keyboard.press("Escape")
    expect(settings).not_to_have_class(E2E_ACTIVE)
    expect(body).not_to_have_class(NO_SCROLL)


def test_チュートリアル中の設定をEscで閉じるとチュートリアルも終わる(e2e):
    page = e2e.open(welcome=True)
    with e2e.precondition():
        expect(page.locator(WELCOME)).to_have_class(OPEN)
    page.locator("#welcome-start-btn").click()
    settings, banner = page.locator(SETTINGS), page.locator(TUTORIAL_BANNER)
    with e2e.precondition():
        expect(settings).to_have_class(E2E_ACTIVE)
        expect(banner).to_be_visible()

    page.keyboard.press("Escape")
    expect(settings).not_to_have_class(E2E_ACTIVE)
    # 閉じた設定の中なので見えないのは当たり前。チュートリアルを終えたか（× と同じく endTutorial を呼んだか）は display で見る
    expect(banner).to_have_css("display", "none")
    expect(page.locator(".tutorial-highlight")).to_have_count(0)
    expect(page.locator("body")).not_to_have_class(NO_SCROLL)


# フォルダ選びの偽の応答（コンテナのフォルダは読まない。同期の設定は E2ESite.open_dir_browser が偽の応答にする）
FAKE_DIRS = {"current": "/e2e-元", "parent": "/", "dirs": [{"name": "サブ", "path": "/e2e-元/サブ"}]}


def test_設定の中のフォルダ選びはEsc1回目でフォルダ選びだけ閉じ2回目で設定を閉じる(e2e):
    page = e2e.open()
    e2e.open_dir_browser(page, json=FAKE_DIRS)
    settings, dir_browser = page.locator(SETTINGS), page.locator(E2E_DIR_BROWSER)
    with e2e.precondition():
        expect(dir_browser).to_have_class(E2E_ACTIVE)
        expect(page.locator("#dir-current-path")).to_have_text(FAKE_DIRS["current"])

    page.keyboard.press("Escape")
    expect(dir_browser).not_to_have_class(E2E_ACTIVE)
    expect(settings).to_have_class(E2E_ACTIVE)
    expect(page.locator("#setting-content-src")).to_have_value(E2E_FAKE_SYNC_CONFIG["content_src"])   # 選ばずに閉じる

    page.keyboard.press("Escape")
    expect(settings).not_to_have_class(E2E_ACTIVE)


# ---------- 背景のスクロールの固定（B-24・X-11） ----------

def _expect_wheel_does_not_scroll(page, below=SEARCH_CONTENT):
    """モーダルの中身（below）の下の暗幕でホイールを回しても、本文がスクロールしない（動き出すまで 2 フレーム待ってから見る）"""
    content = page.locator(below).bounding_box()
    viewport = page.viewport_size
    x = viewport["width"] / 2
    y = (content["y"] + content["height"] + viewport["height"]) / 2
    before = page.evaluate("document.scrollingElement.scrollTop")
    page.mouse.move(x, y)
    page.mouse.wheel(0, 600)
    page.evaluate("() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))")
    assert page.evaluate("document.scrollingElement.scrollTop") == before, "モーダルの裏で本文がスクロールした"


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


def test_画像の拡大を開いているあいだは裏の本文がスクロールせず閉じると固定が外れる(e2e):
    page = e2e.open(E2E_IMAGE_NOTE)
    lightbox, body = page.locator(LIGHTBOX), page.locator("body")
    page.locator(".markdown-body img.obsidian-image").click()
    with e2e.precondition():
        expect(lightbox).to_have_class(E2E_ACTIVE)

    expect(body).to_have_class(NO_SCROLL)
    _expect_wheel_does_not_scroll(page, below=LIGHTBOX_IMAGE)

    page.keyboard.press("Escape")
    expect(lightbox).not_to_have_class(E2E_ACTIVE)
    expect(body).not_to_have_class(NO_SCROLL)


# ---------- つながりの歩数のラジオ（B-25） ----------

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
    "S",
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
