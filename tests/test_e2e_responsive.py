"""画面の幅で変わる動きの E2E（768px をまたいだとき・768px 以下の「＋」。Q-17。仕組みは conftest.py の e2e）

- つながり: 開いたまま 768px をまたいでも開いたまま。PC は右上のパネル、768px 以下は下からのシート＋暗幕。
  閉じたときのフォーカスの戻し先は、PC はつながりのボタン、768px 以下は「＋」。枠の幅が変わったら描き直す（local-graph.js）
- 768px 以下の「＋」: 開くと最初の項目へ、Esc で閉じて「＋」へ戻る。Tab で外へ出ると閉じる（フォーカスは奪わない）。
  項目から G でつながりを開くと「＋」はしまう（article-dial.js）。中から ? で開いた一覧を閉じると、見える場所へ戻る（B-26）
- ⋮: 768px 以下は「＋」の中（#article-dial-menu）、PC は記事ヘッダーの元の場所。またぐと ⋮ のドロップダウンを閉じる
- スマホのドロワー: 目次の項目を押したあと・開いたまま PC の幅に広げたあとも、本文はスクロールできる（sidebar.js）
- エディタ: 境目をドラッグしてから 768px 以下にしても、縦に並んだ入力欄とプレビューは同じ高さ（editor.js）
  タッチでもドラッグできる（769px 以上のタブレットなど）。768px 以下ではタッチのスクロールを止めない（X-12）

直っていない不具合（ロードマップの ID）は、直したら通るテストを xfail(strict=True) で置く（書き方の約束は
CLAUDE.md の Testing と conftest.py の E2ESite.precondition）。直して通るようになると XPASS で落ちるので、そのときは印を外す
"""
import re

from conftest import (E2E_ACTIVE, E2E_EDITOR_RESIZER, E2E_GRAPH_BUTTON, E2E_GRAPH_PANEL, E2E_PC, E2E_PHONE,
                      E2E_SHORTCUT_SHEET, import_playwright)

expect = import_playwright().expect

GRAPH_BACKDROP = ".local-graph-backdrop"
DIAL = "#article-dial"
DIAL_TOGGLE = "#article-dial-toggle"
PAGE_MENU = ".page-menu-container"
PAGE_MENU_BUTTON = "#page-menu-btn"
PAGE_MENU_DROPDOWN = "#page-menu-dropdown"
SIDEBAR = "#sidebar"

IS_OPEN = re.compile(r"\bis-open\b")
SHOW = re.compile(r"\bshow\b")
OVERFLOW = re.compile(r"overflow")
RESIZING = re.compile(r"\beditor-resizing\b")    # エディタの境目をドラッグしているあいだ body に付くクラス
# エディタの境目を左端までドラッグしたあとの入力欄の幅の上限（枠に対する割合。editor.js は 2 割より狭くしない）。
# 半分ずつの初めの幅でも「入力欄 < プレビュー」になる（プレビューの左の線のぶん）ので、プレビューとは比べない
DRAGGED_TO_LEFT = 0.3


def _wait_graph_fits(e2e, page, before=None) -> int:
    """
    つながりのグラフが枠の幅で描かれるまで待ち、枠の幅を返す（svg の width ＝ 枠の幅）
    before を渡すと、枠の幅がそれから変わって描き直されるまで待つ
    """
    e2e.wait_until(page, """before => {
        const canvas = document.querySelector('#local-graph .local-graph-canvas');
        const svg = canvas.querySelector('svg');
        return Boolean(svg) && canvas.clientWidth > 0 && canvas.clientWidth !== before
            && Number(svg.getAttribute('width')) === canvas.clientWidth;
    }""", "つながりのグラフが枠の幅で描き直されない", arg=before)
    return page.evaluate("document.querySelector('#local-graph .local-graph-canvas').clientWidth")


def _focus_is_outside_dial(page) -> bool:
    return page.evaluate("""() => {
        const el = document.activeElement;
        return el !== document.body && !document.getElementById('article-dial').contains(el);
    }""")


# ---------- つながり（768px をまたぐ） ----------

def test_つながりは開いたまま768pxをまたぐとパネルとシートが入れ替わりフォーカスの戻し先と描画も合う(e2e):
    page = e2e.open(width=E2E_PC)
    panel = page.locator(E2E_GRAPH_PANEL)
    page.keyboard.press("g")
    expect(panel).to_be_visible()
    pc_width = _wait_graph_fits(e2e, page)

    # PC → スマホ: 開いたまま下からのシート（暗幕付き）になり、枠の幅で描き直す。閉じると「＋」へ戻る
    e2e.resize(page, E2E_PHONE)
    expect(panel).to_be_visible()
    expect(panel).to_have_css("position", "fixed")
    expect(page.locator(GRAPH_BACKDROP)).to_be_visible()
    phone_width = _wait_graph_fits(e2e, page, before=pc_width)
    assert phone_width > pc_width
    page.keyboard.press("Escape")
    expect(panel).to_be_hidden()
    expect(page.locator(DIAL_TOGGLE)).to_be_focused()

    # スマホ → PC: 開いたまま右上のパネルに戻り、暗幕は消える。閉じるとつながりのボタンへ戻る
    page.keyboard.press("g")
    expect(panel).to_be_visible()
    _wait_graph_fits(e2e, page)
    e2e.resize(page, E2E_PC)
    expect(panel).to_be_visible()
    expect(panel).to_have_css("position", "absolute")
    expect(page.locator(GRAPH_BACKDROP)).to_be_hidden()
    assert _wait_graph_fits(e2e, page, before=phone_width) == pc_width
    page.keyboard.press("Escape")
    expect(panel).to_be_hidden()
    expect(page.locator(E2E_GRAPH_BUTTON)).to_be_focused()


# ---------- 768px 以下の「＋」 ----------

def test_スマホのプラスは開くと最初の項目へ移りEscで閉じてプラスへ戻る(e2e):
    page = e2e.open(width=E2E_PHONE)
    dial, toggle = page.locator(DIAL), page.locator(DIAL_TOGGLE)

    toggle.click()
    expect(dial).to_have_class(IS_OPEN)
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(page.locator(E2E_GRAPH_BUTTON)).to_be_focused()     # 最初の項目は「つながり」

    page.keyboard.press("Escape")
    expect(dial).not_to_have_class(IS_OPEN)
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(toggle).to_be_focused()


def test_スマホのプラスはTabで外へ出ると閉じフォーカスは奪わない(e2e):
    page = e2e.open(width=E2E_PHONE)
    dial = page.locator(DIAL)
    page.locator(DIAL_TOGGLE).click()
    expect(page.locator(E2E_GRAPH_BUTTON)).to_be_focused()

    # 「＋」の中の項目（つながり・⋮）を Tab で進み、外へ出るまで押す
    for _ in range(5):
        page.keyboard.press("Tab")
        if _focus_is_outside_dial(page):
            break
    assert _focus_is_outside_dial(page)
    expect(dial).not_to_have_class(IS_OPEN)
    assert _focus_is_outside_dial(page)     # 閉じても「＋」へ引き戻さない


def test_スマホのプラスの項目からGでつながりを開くとプラスはしまいフォーカスはつながりに残る(e2e):
    page = e2e.open(width=E2E_PHONE)
    dial = page.locator(DIAL)
    page.locator(DIAL_TOGGLE).click()
    expect(page.locator(E2E_GRAPH_BUTTON)).to_be_focused()

    page.keyboard.press("g")
    expect(page.locator(E2E_GRAPH_PANEL)).to_be_visible()
    expect(dial).not_to_have_class(IS_OPEN)
    expect(page.locator(E2E_GRAPH_PANEL)).to_be_focused()


# ---------- ⋮（768px をまたぐ） ----------

def test_縦三点は768px以下でプラスの中へPCで元の場所へ戻りまたぐとドロップダウンが閉じる(e2e):
    page = e2e.open(width=E2E_PC)
    dropdown = page.locator(PAGE_MENU_DROPDOWN)
    in_header = page.locator(f".view-header-actions > {PAGE_MENU}:last-child")
    in_dial = page.locator(f"#article-dial-menu > {PAGE_MENU}")
    expect(in_header).to_have_count(1)

    # PC で開いたまま 768px 以下へ: 「＋」の中へ移り、ドロップダウンは閉じる
    page.locator(PAGE_MENU_BUTTON).click()
    expect(dropdown).to_have_class(SHOW)
    e2e.resize(page, E2E_PHONE)
    expect(in_dial).to_have_count(1)
    expect(in_header).to_have_count(0)
    expect(dropdown).not_to_have_class(SHOW)
    expect(page.locator(PAGE_MENU_BUTTON)).to_have_attribute("aria-expanded", "false")

    # 「＋」の中で開いたまま PC へ: 元の場所へ戻り、ドロップダウンも「＋」も閉じる
    page.locator(DIAL_TOGGLE).click()
    page.locator(PAGE_MENU_BUTTON).click()
    expect(dropdown).to_have_class(SHOW)
    e2e.resize(page, E2E_PC)
    expect(in_header).to_have_count(1)
    expect(in_dial).to_have_count(0)
    expect(dropdown).not_to_have_class(SHOW)
    expect(page.locator(DIAL)).not_to_have_class(IS_OPEN)


# ---------- 768px 以下の「＋」の中から ?（B-26） ----------

def test_スマホのプラスの中からクエスチョンで開いた一覧をEscで閉じるとフォーカスが見える場所へ戻る(e2e):
    page = e2e.open(width=E2E_PHONE)
    dial = page.locator(DIAL)
    page.locator(DIAL_TOGGLE).click()
    with e2e.precondition():
        expect(page.locator(E2E_GRAPH_BUTTON)).to_be_focused()
    page.keyboard.press("?")
    with e2e.precondition():
        expect(page.locator(E2E_SHORTCUT_SHEET)).to_have_class(E2E_ACTIVE)

    # 今の作りでは、一覧へフォーカスが移ると「＋」が閉じる。閉じたときは閉じ切る（項目が隠れる）まで待ってから Esc を押す
    # （閉じかけのあいだは項目がまだ見えていて、そこへ戻れてしまう）。＋を開いたままにする直し方なら待たない
    dial_closed = "is-open" not in (dial.get_attribute("class") or "")
    if dial_closed:
        expect(page.locator(E2E_GRAPH_BUTTON)).to_be_hidden()
    page.keyboard.press("Escape")
    with e2e.precondition():
        expect(page.locator(E2E_SHORTCUT_SHEET)).not_to_have_class(E2E_ACTIVE)

    # ＋が閉じたなら＋へ、開いたままなら開く前の項目へ戻る（どちらも見えている場所。body に落ちない）
    expect(page.locator(DIAL_TOGGLE if dial_closed else E2E_GRAPH_BUTTON)).to_be_focused()


# ---------- スマホのドロワー（B-22・B-23） ----------

def _open_drawer(e2e, page):
    page.locator("#sidebar-toggle-mobile").click()
    with e2e.precondition():
        expect(page.locator(SIDEBAR)).to_have_class(E2E_ACTIVE)


def _expect_wheel_scrolls(e2e, page):
    """本文の上（本文の横の真ん中・画面の縦の真ん中）でホイールを回すと、本文がスクロールする"""
    body = page.locator(".markdown-body").bounding_box()
    x = body["x"] + body["width"] / 2
    y = page.viewport_size["height"] / 2
    before = page.evaluate("document.scrollingElement.scrollTop")
    page.mouse.move(x, y)
    page.mouse.wheel(0, 300)
    e2e.wait_until(page, "before => document.scrollingElement.scrollTop !== before",
                   "ホイールで本文がスクロールしない", arg=before)


def test_スマホで目次の項目を押したあとも本文をスクロールできる(e2e):
    page = e2e.open(width=E2E_PHONE)
    _open_drawer(e2e, page)
    page.locator(".sidebar-tab[data-panel='sidebar-outline']").click()
    page.locator("#sidebar-outline .toc-item.toc-h2").click()
    with e2e.precondition():
        expect(page.locator(SIDEBAR)).not_to_have_class(E2E_ACTIVE)
        # 見出しへの smooth スクロールが止まるまで待つ（100ms ごとに見て、位置が変わらなくなったら止まった）
        e2e.wait_until(page, """() => {
            const y = document.scrollingElement.scrollTop;
            const settled = y > 0 && window.__e2eLastScrollTop === y;
            window.__e2eLastScrollTop = y;
            return settled;
        }""", "目次の見出しへのスクロールが止まらない", polling=100)

    expect(page.locator("body")).not_to_have_attribute("style", OVERFLOW)
    _expect_wheel_scrolls(e2e, page)


def test_スマホのドロワーを開いたままPCの幅に広げてもドロワーとスクロールの固定が残らない(e2e):
    page = e2e.open(width=E2E_PHONE)
    _open_drawer(e2e, page)
    e2e.resize(page, E2E_PC)

    expect(page.locator(SIDEBAR)).not_to_have_class(E2E_ACTIVE)
    expect(page.locator("body")).not_to_have_attribute("style", OVERFLOW)
    _expect_wheel_scrolls(e2e, page)


# ---------- エディタの境目（X-10） ----------

def test_エディタの境目をドラッグしてからスマホの幅にしても入力欄とプレビューは同じ高さ(e2e):
    page = e2e.open_path("/editor")
    input_pane, preview_pane = page.locator(".editor-input-pane"), page.locator(".editor-preview-pane")
    resizer = page.locator(E2E_EDITOR_RESIZER).bounding_box()
    panes = page.locator(".editor-panes").bounding_box()
    y = resizer["y"] + resizer["height"] / 2
    page.mouse.move(resizer["x"] + resizer["width"] / 2, y)
    page.mouse.down()
    page.mouse.move(panes["x"], y, steps=5)     # 左端まで
    page.mouse.up()
    with e2e.precondition():
        assert input_pane.bounding_box()["width"] < panes["width"] * DRAGGED_TO_LEFT, "ドラッグで入力欄が狭くならない"

    e2e.resize(page, E2E_PHONE)
    e2e.wait_until(page, """() => {
        const height = selector => document.querySelector(selector).getBoundingClientRect().height;
        return Math.abs(height('.editor-input-pane') - height('.editor-preview-pane')) <= 10;
    }""", "縦に並んだ入力欄とプレビューの高さがそろわない")


def test_エディタの境目はタッチでもドラッグできスマホの幅ではタッチのスクロールを止めない(e2e):
    page = e2e.open_path("/editor")
    input_pane = page.locator(".editor-input-pane")
    resizer = page.locator(E2E_EDITOR_RESIZER)
    box = resizer.bounding_box()
    panes = page.locator(".editor-panes").bounding_box()
    # 境目に届いた入力の種類を記録する（マウスではなくタッチとして届いたことを確かめる）
    page.evaluate("""() => {
        window.resizerPointerTypes = [];
        document.getElementById('editor-resizer')
            .addEventListener('pointerdown', e => window.resizerPointerTypes.push(e.pointerType));
    }""")
    # 指で左端までなぞる。CDP のタッチはブラウザが本物のタッチとして扱う（pointerType が touch の pointer events になり、
    # touch-action が許していればスクロールに回して pointercancel を出す）。Playwright の touchscreen は tap しか無い
    cdp = page.context.new_cdp_session(page)
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
    for step in range(1, 6):
        cdp.send("Input.dispatchTouchEvent",
                 {"type": "touchMove", "touchPoints": [{"x": x - (x - panes["x"]) * step / 5, "y": y}]})
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})

    assert page.evaluate("window.resizerPointerTypes") == ["touch"]
    assert input_pane.bounding_box()["width"] < panes["width"] * DRAGGED_TO_LEFT, "タッチのドラッグで入力欄が狭くならない"
    expect(page.locator("body")).not_to_have_class(RESIZING)   # 指を離したらドラッグを終える

    # 768px 以下はドラッグしないので、境目に触れてもページはスクロールできる
    e2e.resize(page, E2E_PHONE)
    expect(resizer).to_have_css("touch-action", "auto")
