"""ページの CSP（S-10）の E2E（仕組みは conftest.py の e2e）

ノートに書いた生の HTML は、サニタイズ（Python 側）と CSP の二段で止める。ここでは CSP の側を見る。
ポリシーは app/config.py の CONTENT_SECURITY_POLICY（script-src は 'self' と先読みの hash だけ。インラインの script・
イベント属性・javascript: の URL・eval は動かない）。

- 違反 0: 主な画面（一覧・記事（数式・Mermaid・コード・カードリンク・画像）・つながり・グラフ・ダッシュボード・エディタ・
  ヘルプの各タブ・検索・エラー画面）を管理者と外部の人で開いても、CSP の違反が出ない。
  違反は conftest.py の e2e がどのテストでも拾って終わりに 0 件を確かめる。ここでは画面ごとにも確かめる
- 動き: インラインから外のファイルへ移したスクリプトが、今までどおり動く
  - 描く前に <html> にテーマ・サイドバーの開閉と幅・読みやすい幅・文字サイズ・プロパティの開閉と、コードの配色が付いている
    （before-paint.js。後から付けるとちらつく）
  - コードの配色を設定で切り替えられる（window.codeThemeHref）
  - 数式を KaTeX で描く（article-math.js）
  - 一覧は、並び替えと公開状態を変えると送り、検索欄に打っただけでは送らない（hx-trigger の from:。HTMX の eval を使わない）
  - 先読み（speculationrules）は hash で許すので止まらない（ブラウザが speculationrules を読むことと、違反 0 で見る）
- 守り: ノートに書いた <script>・onerror・javascript: のリンクが動かない。サニタイズをすり抜けた HTML がページに
  入っても、CSP だけで止まる（違反として報告される）
- Mermaid は securityLevel: 'strict'。点の click でページの関数を呼ばせず、ラベルの <br/> は改行として描く
"""
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from app import cache
from conftest import (E2E_ADMIN, E2E_GRAPH_PANEL, E2E_MERMAID_CALLBACK, E2E_RAW_HTML_NOTE, E2E_RICH_NOTE, E2E_VIEWERS,
                      import_playwright)

expect = import_playwright().expect

ARTICLE = ".markdown-body"
MERMAID_SVG = f"{ARTICLE} .mermaid svg"
HELP_TABS = "#help-modal .help-tab"
QUICK_SWITCHER_INPUT = "#modal-search-input"
QUICK_SWITCHER_ITEMS = "#modal-search-results .search-result-item"

# 待ちの済んだタスク（CSP の違反の知らせなど）を流し終えるまで待つ
_FLUSH_TASKS = "() => new Promise(resolve => requestAnimationFrame(() => setTimeout(resolve, 0)))"


def _expect_no_violations(page, where: str) -> None:
    """今のページで CSP の違反が出ていない（知らせは少し遅れて届くので、待ちの済んだタスクを流してから見る）"""
    page.evaluate(_FLUSH_TASKS)
    violations = page.evaluate("window.__e2eCspViolations")
    assert violations == [], f"{where}で CSP の違反が出た: {violations}"


def _is_list_request(request) -> bool:
    """一覧（/）の部分読み込み（HTMX）のリクエストか"""
    return bool(request.headers.get("hx-request")) and urlsplit(request.url).path == "/"


# 一覧の領域（#search-interactive-area）を HTMX が差し替えて読み終えた（settle）回数を、window.__e2eListSettled に数える
_COUNT_LIST_SETTLED = """() => {
    window.__e2eListSettled = 0;
    document.addEventListener('htmx:afterSettle', (event) => {
        if (event.target.id === 'search-interactive-area') window.__e2eListSettled++;
    });
}"""


def _send_list(e2e, page, action, settled: int) -> None:
    """
    一覧を送る操作をして、差し替えた一覧を HTMX が読み終えるまで待つ（settled は読み終えた回数の合計）

    HTMX は差し替えた中身を少しあと（settle）で読むので、読み終える前に欄を変えても change を拾わない
    """
    with page.expect_response(lambda response: _is_list_request(response.request)):
        action()
    e2e.wait_until(page, "n => window.__e2eListSettled >= n", "一覧の差し替えが終わらない", arg=settled)


# ---------- 違反 0（主な画面） ----------

@pytest.mark.parametrize("viewer", E2E_VIEWERS)
def test_記事の数式とMermaidとコードとカードリンクと画像をCSPの違反なしに描く(e2e, viewer):
    page = e2e.open(E2E_RICH_NOTE, viewer=viewer)
    expect(page.locator(f"{ARTICLE} .math.inline .katex")).to_have_count(1)
    expect(page.locator(f"{ARTICLE} .math.block .katex-display")).to_have_count(1)
    expect(page.locator(MERMAID_SVG)).to_have_count(1)
    expect(page.locator(f"{ARTICLE} pre code.hljs")).to_have_count(1)
    expect(page.locator(f"{ARTICLE} .link-card-image")).to_have_count(1)
    e2e.wait_until(page, f"""() => {{
        const img = document.querySelector('{ARTICLE} img');
        return Boolean(img) && img.complete && img.naturalWidth > 0;
    }}""", "本文の画像が読み込まれない")
    # 先読みのルールをブラウザが読む（読まないブラウザだと、ルールが CSP で止まるかを見られない）
    assert page.evaluate("HTMLScriptElement.supports('speculationrules')")
    _expect_no_violations(page, "記事")


@pytest.mark.parametrize("viewer", E2E_VIEWERS)
def test_つながりのグラフをCSPの違反なしに描く(e2e, viewer):
    page = e2e.open(viewer=viewer)
    page.keyboard.press("g")
    expect(page.locator(f"{E2E_GRAPH_PANEL} svg circle").first).to_be_visible()
    _expect_no_violations(page, "つながり")


@pytest.mark.parametrize("viewer", E2E_VIEWERS)
def test_一覧と検索をCSPの違反なしに使える(e2e, viewer):
    page = e2e.open_path("/", viewer=viewer)
    expect(page.locator("#file-tree .tree-file").first).to_be_visible()
    _expect_no_violations(page, "一覧")

    # 一覧の検索欄（HTMX で一覧を差し替える）
    page.evaluate(_COUNT_LIST_SETTLED)
    search_input = page.locator(".search-input")
    search_input.fill(e2e.SEARCH_WORD)
    _send_list(e2e, page, lambda: search_input.press("Enter"), 1)
    expect(page.locator(".search-input")).to_have_value(e2e.SEARCH_WORD)
    _expect_no_violations(page, "一覧の検索")

    # クイックスイッチャー
    page.keyboard.press("Control+k")
    page.locator(QUICK_SWITCHER_INPUT).fill(e2e.SEARCH_WORD)
    expect(page.locator(QUICK_SWITCHER_ITEMS).first).to_be_visible()
    _expect_no_violations(page, "クイックスイッチャー")


@pytest.mark.parametrize("viewer", E2E_VIEWERS)
def test_全体のグラフをCSPの違反なしに描く(e2e, viewer):
    page = e2e.open_path("/graph", viewer=viewer)
    expect(page.locator("#graph-canvas svg circle").first).to_be_visible()
    _expect_no_violations(page, "全体のグラフ")


@pytest.mark.parametrize("viewer", E2E_VIEWERS)
def test_ヘルプの各タブをCSPの違反なしに開ける(e2e, viewer):
    page = e2e.open(viewer=viewer)
    page.locator("#help-open-btn").click()
    tabs = page.locator(HELP_TABS)
    expect(tabs.first).to_be_visible()
    for i in range(tabs.count()):
        tab = tabs.nth(i)
        tab.click()
        expect(page.locator(f"#help-panel-{tab.get_attribute('data-tab')}")).to_be_visible()
        _expect_no_violations(page, f"ヘルプの「{tab.text_content()}」タブ")


@pytest.mark.parametrize("viewer", E2E_VIEWERS)
def test_エラー画面をCSPの違反なしに出す(e2e, viewer):
    page = e2e.open_path("/view/無いノート", viewer=viewer)
    expect(page.locator(".error-page")).to_be_visible()
    _expect_no_violations(page, "エラー画面")


def test_ダッシュボードをCSPの違反なしに出す(e2e):
    page = e2e.open_path("/dashboard", viewer=E2E_ADMIN)
    expect(page.locator(".health-card").first).to_be_visible()
    _expect_no_violations(page, "ダッシュボード")


def test_エディタのプレビューをCSPの違反なしに描く(e2e):
    page = e2e.open_path(f"/editor?path={quote(cache.PATH_TO_SLUG[E2E_RICH_NOTE])}", viewer=E2E_ADMIN)
    preview = page.locator("#editor-preview")
    expect(preview.locator(".mermaid svg")).to_have_count(1)
    expect(preview.locator("pre code.hljs")).to_have_count(1)
    _expect_no_violations(page, "エディタ")


# ---------- 動き（外のファイルへ移したスクリプト） ----------

# <body> ができた時点（描く前）の <html> の状態を、window.__e2eAtBody に残す
_RECORD_AT_BODY = """
new MutationObserver((records, observer) => {
    if (!document.body) return;
    observer.disconnect();
    const html = document.documentElement;
    const link = document.getElementById('highlight-theme');
    window.__e2eAtBody = {
        theme: html.getAttribute('data-theme'),
        classes: [...html.classList].sort(),
        sidebarWidth: html.style.getPropertyValue('--sidebar-width'),
        codeTheme: link ? link.getAttribute('href') : null,
    };
}).observe(document, { childList: true, subtree: true });
"""

_SAVED_SETTINGS = {"theme": "letter", "sidebarCollapsed": "true", "sidebarWidth": "333", "readableWidth": "false",
                   "fontSize": "large", "propertiesOpen": "false", "codeTheme": "nord"}


@pytest.mark.parametrize("saved, expected", [
    pytest.param({}, {"theme": "dark", "classes": ["font-medium", "readable-width"], "sidebarWidth": "",
                      "codeTheme": "/static/css/themes/github-dark.min.css"}, id="既定"),
    pytest.param(_SAVED_SETTINGS, {"theme": "letter", "classes": ["font-large", "properties-collapsed", "sidebar-collapsed"],
                                   "sidebarWidth": "333px", "codeTheme": "/static/css/themes/nord.min.css"}, id="保存した設定"),
])
def test_描く前にhtmlに保存した表示の状態とコードの配色が付いている(e2e, saved, expected):
    page = e2e.open()
    # open が入れたサイドバーを開く設定のあとに走るので、ここで入れた値が勝つ
    page.context.add_init_script(
        "".join(f"localStorage.setItem({key!r}, {value!r});" for key, value in saved.items()) + _RECORD_AT_BODY)
    page.reload()
    e2e.wait_ready(page)
    assert page.evaluate("window.__e2eAtBody") == expected


def test_コードの配色を設定で切り替えられる(e2e):
    page = e2e.open(E2E_RICH_NOTE)
    page.locator("#settings-open-btn").click()
    page.locator("#setting-code-theme").select_option("dracula")
    expect(page.locator("#highlight-theme")).to_have_attribute("href", "/static/css/themes/dracula.min.css")


def test_一覧は並び替えと公開状態を変えると送り検索欄に打っただけでは送らない(e2e):
    page = e2e.open_path("/", viewer=E2E_ADMIN)
    page.evaluate(_COUNT_LIST_SETTLED)
    sent = []
    page.on("request", lambda request: sent.append(request.url) if _is_list_request(request) else None)

    _send_list(e2e, page, lambda: page.locator(".list-sort-select").select_option("title"), 1)
    expect(page.locator(".list-sort-select")).to_have_value("title")

    # 一覧の領域は outerHTML で差し替わる。差し替わったあとの公開状態でも送る
    _send_list(e2e, page, lambda: page.locator("label[for='v-private']").click(), 2)
    expect(page.locator("#v-private")).to_be_checked()

    # 検索欄は、打って離れても（change が起きても）送らない。Enter で送る
    search_input = page.locator(".search-input")
    search_input.fill("先")
    search_input.press("Tab")
    _send_list(e2e, page, lambda: search_input.press("Enter"), 3)

    queries = [parse_qs(urlsplit(url).query) for url in sent]
    assert len(queries) == 3, f"送った回数が違う（検索欄に打っただけで送っていないか）: {sent}"
    assert queries[0].get("sort") == ["title"]
    assert queries[1].get("visibility") == ["private"]
    assert queries[2].get("q") == ["先"]
    _expect_no_violations(page, "一覧の並び替え・公開状態")


# ---------- Mermaid（securityLevel: 'strict'） ----------

def test_Mermaidは点のclickでページの関数を呼ばずラベルのbrは改行として描く(e2e):
    page = e2e.open(E2E_RICH_NOTE)
    svg = page.locator(MERMAID_SVG)
    expect(svg).to_have_count(1)
    # 式が関数を返すと evaluate がそれを呼んでしまうので、関数の中で置く
    page.evaluate(f"() => {{ window.{E2E_MERMAID_CALLBACK} = () => {{ window.__e2eMermaidCalled = true; }}; }}")

    svg.locator(".node", has_text="押せる点").click()
    page.evaluate(_FLUSH_TASKS)
    assert page.evaluate("window.__e2eMermaidCalled") is None, "Mermaid の click でページの関数が呼ばれた"

    label = svg.locator(".node", has_text="一行目")
    expect(label.locator("br")).to_have_count(1)
    assert "<br" not in svg.text_content(), "ラベルの <br/> が文字のまま出た"


# ---------- 守り ----------

@pytest.mark.parametrize("viewer", E2E_VIEWERS)
def test_ノートに書いたscriptとonerrorとjavascriptのリンクは動かない(e2e, viewer):
    # サニタイズで消えても CSP で止まっても通る（どちらで止まったかは問わない。CSP だけで止まることは次のテストで見る）
    page = e2e.open(E2E_RAW_HTML_NOTE, viewer=viewer)
    e2e.wait_until(page, f"() => [...document.querySelectorAll('{ARTICLE} img')].every(img => img.complete)",
                   "本文の画像の読み込みが終わらない")
    page.locator(ARTICLE).get_by_text("動いてはいけないリンク").click()
    page.evaluate(_FLUSH_TASKS)
    ran = page.evaluate("[window.__e2eNoteScript, window.__e2eNoteOnerror, window.__e2eNoteLink]")
    assert ran == [None, None, None], f"ノートに書いたスクリプトが動いた（script・onerror・javascript: の順）: {ran}"
    e2e.take_csp_violations()   # CSP で止まったときの違反（わざと起こしたもの）


@pytest.mark.parametrize("viewer", E2E_VIEWERS)
def test_サニタイズをすり抜けたHTMLもCSPだけで止まる(e2e, viewer):
    # ページの JS がノートの HTML を入れる（エディタのプレビュー・HTMX の差し替えなど）のと同じく、本文に HTML を入れる
    page = e2e.open(viewer=viewer)
    page.evaluate(f"""() => {{
        const body = document.querySelector('{ARTICLE}');
        const script = document.createElement('script');
        script.textContent = 'window.__e2eInjectedScript = 1';
        body.append(script);
        body.insertAdjacentHTML('beforeend',
            '<img src="/static/images/e2e-missing.png" onerror="window.__e2eInjectedOnerror = 1">' +
            '<a id="e2e-injected-link" href="javascript:window.__e2eInjectedLink = 1">リンク</a>');
    }}""")
    page.locator("#e2e-injected-link").click()
    e2e.wait_until(page, "() => window.__e2eCspViolations.length >= 3", "CSP の違反が 3 件（script・onerror・javascript:）出ない")
    ran = page.evaluate("[window.__e2eInjectedScript, window.__e2eInjectedOnerror, window.__e2eInjectedLink]")
    assert ran == [None, None, None], f"入れたスクリプトが動いた（script・onerror・javascript: の順）: {ran}"
    directives = sorted(text.split(" ")[1] for text in page.evaluate("window.__e2eCspViolations"))
    assert directives == ["script-src-attr", "script-src-elem", "script-src-elem"], directives
    e2e.take_csp_violations()
