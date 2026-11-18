"""ページを移るときの E2E（Q-36。仕組みは conftest.py の e2e）

- ページを移るとき（本文のリンク・ツリーなど、同じサイトの中のリンク）は、View Transition を使わない。
  前は base.css の @view-transition（D-14）で本文を入れ替える動きを付けていたが、遷移の仕組みそのものに
  約 0.3 秒かかり（動きの長さを削っても縮まらない）、クリックしてから表示までが遅れていた
- テーマの切り替え（settings.js の document.startViewTransition）は、同じページの中の遷移なので残す

新しいページの pagereveal の event.viewTransition で、遷移が使われたかを見る
"""
from conftest import import_playwright

expect = import_playwright().expect

# 新しいページで、遷移が使われたかを記録する（ページの JS より先に動く）
_WATCH_REVEAL = """
window.__pageRevealTransition = null;
window.addEventListener('pagereveal', e => { window.__pageRevealTransition = Boolean(e.viewTransition); });
"""


def test_本文のリンクで移るときにページの遷移を使わない(e2e):
    page = e2e.open()
    page.add_init_script(_WATCH_REVEAL)
    before = page.url
    page.locator(".markdown-body a.internal-link").first.click()
    page.wait_for_url(lambda url: url != before)
    e2e.wait_until(page, "() => window.__pageRevealTransition !== null", "新しいページで pagereveal が来ない")
    assert page.evaluate("window.__pageRevealTransition") is False, "ページを移るときに View Transition が使われた"
