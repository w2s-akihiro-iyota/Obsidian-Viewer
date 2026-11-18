"""サーバーやノートから来た文字を、HTML として描かずに文字のまま出す E2E（S-8・S-9。仕組みは conftest.py の e2e）

- フォルダ選び: フォルダ名と、一覧を取れなかったときのサーバーの文言（例外の文字列。パスが入る）（settings.js。S-8）
- リンクのプレビュー: タイトル（frontmatter の title かファイル名。外部の人にも出る）。本文はサーバーで描いた HTML なので、
  HTML のまま描く（sidebar.js。S-9）
- トースト: 文言（core.js の showToast。S-9）

どれも、HTML の入った文字（HTML_TEXT）がそのままの文字（textContent）で出て、img・b の要素ができず、
onerror も走らない（window.__xss が無いまま）ことを見る。サーバーの応答は page.route で偽にする（本物の設定・フォルダは読まない）
"""
import re

import pytest

from conftest import E2E_ACTIVE, E2E_DIR_BROWSER, E2E_VIEWERS, import_playwright

expect = import_playwright().expect

# HTML の入った文字。innerHTML に入れると img（読み込みに失敗して onerror が走る）と b の要素になる
HTML_TEXT = '<img src=x onerror="window.__xss=1"><b>太字</b>'
INJECTED = "img, b"     # HTML_TEXT を HTML として描いたときにできる要素

DIR_LIST = "#dir-browser-list"
DIR_CURRENT = "/e2e-元"
PREVIEW = ".preview-tooltip.active"
PREVIEW_API = re.compile(r"/api/preview\?")
PREVIEW_BODY_TEXT = "プレビューの本文"
LINK_TEXT = "つながり先のノートA"     # 入口のノート（E2E_ENTRY_NOTE）の本文にあるリンク


def _expect_plain_text(page, text_el, scope):
    """text_el に HTML_TEXT がそのままの文字で出ていて、scope の中に HTML_TEXT からできる要素が無く、onerror も走っていない"""
    expect(text_el).to_have_text(HTML_TEXT)
    # to_have_text は空白をまとめてから比べるので、そのままの文字でも比べる
    assert text_el.text_content() == HTML_TEXT, f"文字が変わった: {text_el.text_content()!r}"
    expect(scope.locator(INJECTED)).to_have_count(0)
    assert page.evaluate("typeof window.__xss") == "undefined", "HTML_TEXT の onerror が走った"


# ---------- フォルダ選び（S-8） ----------

def test_フォルダ選びはフォルダ名にHTMLが入っていても文字のまま出す(e2e):
    page = e2e.open()
    e2e.open_dir_browser(page, json={"current": DIR_CURRENT, "parent": "/",
                                     "dirs": [{"name": HTML_TEXT, "path": f"{DIR_CURRENT}/x"}]})
    with e2e.precondition():
        expect(page.locator(E2E_DIR_BROWSER)).to_have_class(E2E_ACTIVE)
        expect(page.locator("#dir-current-path")).to_have_text(DIR_CURRENT)

    item = page.locator(f"{DIR_LIST} .dir-item:not(.parent-dir)")
    _expect_plain_text(page, item.locator("span"), page.locator(DIR_LIST))
    expect(item.locator("svg")).to_have_count(1)     # フォルダのアイコンは今までどおり


def test_フォルダ選びは一覧を取れなかったときのサーバーの文言にHTMLが入っていても文字のまま出す(e2e):
    page = e2e.open()
    # サーバーは例外の文字列（str(e)。パスが入る）を message に入れて 500 を返す（app/api/sync.py の list_dirs）
    e2e.open_dir_browser(page, status=500, json={"status": "error", "message": HTML_TEXT})
    with e2e.precondition():
        expect(page.locator(E2E_DIR_BROWSER)).to_have_class(E2E_ACTIVE)

    _expect_plain_text(page, page.locator(f"{DIR_LIST} .error-msg"), page.locator(DIR_LIST))


# ---------- リンクのプレビューのタイトル（S-9） ----------

@pytest.mark.parametrize("viewer", E2E_VIEWERS)
def test_リンクのプレビューはタイトルにHTMLが入っていても文字のまま出し本文はHTMLのまま描く(e2e, viewer):
    page = e2e.open(viewer=viewer)
    # テスト用のノートの title は変えず、プレビューの応答だけ偽にする
    page.route(PREVIEW_API, lambda route: route.fulfill(
        json={"title": HTML_TEXT, "content": f"<p>{PREVIEW_BODY_TEXT}</p>"}))
    page.locator(".markdown-body a.internal-link", has_text=LINK_TEXT).first.hover()
    preview = page.locator(PREVIEW)
    with e2e.precondition():
        expect(preview).to_be_visible()

    _expect_plain_text(page, preview.locator(".preview-title"), preview)
    # 本文はサーバーで描いた Markdown の HTML なので、文字にせず HTML のまま描く（<p> が要素になる）
    expect(preview.locator(".preview-content > p")).to_have_text(PREVIEW_BODY_TEXT)


# ---------- トースト（S-9） ----------

def test_トーストは文言にHTMLが入っていても文字のまま出す(e2e):
    page = e2e.open()
    page.evaluate("text => showToast(text, 'error')", HTML_TEXT)
    toast = page.locator("#toast-container .toast-error")
    with e2e.precondition():
        expect(toast).to_have_count(1)

    _expect_plain_text(page, toast.locator("span"), toast)
    expect(toast.locator("svg")).to_have_count(1)    # 種類のアイコンは今までどおり
