"""ページを移るときの E2E（Q-36・B-32。仕組みは conftest.py の e2e）

- ページを移るとき（本文のリンク・ツリーなど、同じサイトの中のリンク）は、View Transition を使わない。
  前は base.css の @view-transition（D-14）で本文を入れ替える動きを付けていたが、遷移の仕組みそのものに
  約 0.3 秒かかり（動きの長さを削っても縮まらない）、クリックしてから表示までが遅れていた
- テーマの切り替え（settings.js の document.startViewTransition）は、同じページの中の遷移なので残す
- 移った先のサイドバーは、最初に描いたときから、前回選んでいたタブ（ファイル・目次・閲覧履歴）のまま出す。
  前は「ファイル」タブで一度描いてから、/api/messages の応答を待って前回のタブに切り替えていて、ちらついた（B-32）。
  タブの中身のフェードインも、ページを開くたびではなく、タブを押したときだけにする
  - 閲覧履歴は、一覧（開いたノートが先頭）も最初の描画から出す（history.js が本文を読みながら描く）
  - ファイルの木と目次は、JS が動いてから描く（木は前に取った木を DOMContentLoaded で。Q-21。目次は本文を読み終えてから）。
    それまでは「まだ描いていない」（読み込み中・空）を許し、違う中身（本文があるのに「見出しがありません」など）は許さない。
    このテストはリクエストを横取りするのでブラウザのキャッシュが効かず、JS が動くまでがふだんより長い

新しいページの pagereveal の event.viewTransition で、遷移が使われたかを見る。
サイドバーは、新しいページで描くたび（requestAnimationFrame。描く直前に呼ばれる）にようすを記録して見る
"""
from urllib.parse import urljoin

import pytest

from conftest import import_playwright

expect = import_playwright().expect

# 新しいページで、遷移が使われたかを記録する（ページの JS より先に動く）
_WATCH_REVEAL = """
window.__pageRevealTransition = null;
window.addEventListener('pagereveal', e => { window.__pageRevealTransition = Boolean(e.viewTransition); });
"""

# 読み込みが終わってから、さらに何回描くまで記録するか
_FRAMES_AFTER_LOAD = 10
# タブの中身を「まだ描いていない」ときの、パネルの最初の項目（ファイルの木の読み込み中・空のパネル）
_NOT_DRAWN_YET = {"読み込み中…", None}

# 新しいページで描くたびに、サイドバーのようすを記録する（ページの JS より先に動く）。
# 選んでいるタブ・見えているパネル・パネルの最初の項目の文字・パネルが動いている（フェードイン）か。
# タブがまだ無い（本文をそこまで読んでいない）ときは記録しない
_RECORD_SIDEBAR_FRAMES = """
window.__e2eSidebarFrames = [];
window.__e2eSidebarFramesDone = false;
(() => {
    let afterLoad = 0;
    const record = () => {
        const tab = document.querySelector('.sidebar-tab.active');
        if (tab) {
            const shown = [...document.querySelectorAll('.sidebar-panel')].filter(p => getComputedStyle(p).display !== 'none');
            const first = shown[0]?.querySelector('.tree-folder, .tree-file, .toc-text, .history-title, .tree-empty, .toc-empty, .history-empty');
            window.__e2eSidebarFrames.push({
                tab: tab.dataset.panel,
                panels: shown.map(p => p.id),
                first: first ? first.textContent.trim() : null,
                fading: shown.some(p => p.getAnimations().length > 0),
            });
        }
        if (document.readyState === 'complete') afterLoad++;
        if (afterLoad < AFTER_LOAD) requestAnimationFrame(record);
        else window.__e2eSidebarFramesDone = true;
    };
    requestAnimationFrame(record);
})();
""".replace("AFTER_LOAD", str(_FRAMES_AFTER_LOAD))


def test_本文のリンクで移るときにページの遷移を使わない(e2e):
    page = e2e.open()
    page.add_init_script(_WATCH_REVEAL)
    before = page.url
    page.locator(".markdown-body a.internal-link").first.click()
    page.wait_for_url(lambda url: url != before)
    e2e.wait_until(page, "() => window.__pageRevealTransition !== null", "新しいページで pagereveal が来ない")
    assert page.evaluate("window.__pageRevealTransition") is False, "ページを移るときに View Transition が使われた"


@pytest.mark.parametrize("panel, drawn_before_paint", [
    pytest.param("sidebar-files", False, id="ファイル"),
    pytest.param("sidebar-outline", False, id="目次"),
    pytest.param("sidebar-history", True, id="閲覧履歴"),
])
def test_移った先のサイドバーは最初の描画から前回のタブのまま(e2e, panel, drawn_before_paint):
    page = e2e.open()
    with e2e.precondition():
        page.locator(f".sidebar-tab[data-panel='{panel}']").click()
        expect(page.locator(f"#{panel}")).to_be_visible()

    # 本文のリンクの先へ移る（クリックではなく goto にする。マウスを乗せると先読み（F-15）が走り、
    # 先読みしたページにはこの記録が入らないことがある）
    href = page.locator(".markdown-body a.internal-link").first.get_attribute("href")
    page.add_init_script(_RECORD_SIDEBAR_FRAMES)
    page.goto(urljoin(page.url, href))
    e2e.wait_ready(page)
    e2e.wait_until(page, "() => window.__e2eSidebarFramesDone", "新しいページで描いたようすを記録し終わらない")

    frames = page.evaluate("window.__e2eSidebarFrames")
    last = frames[-1]
    assert last["first"] and last["first"] not in _NOT_DRAWN_YET, f"タブの中身が描かれていない: {last}"
    if panel == "sidebar-history":
        assert last["first"] == page.title().replace(" - Obsidian Viewer", ""), f"開いたノートが閲覧履歴の先頭に無い: {last}"

    shown = {"tab": panel, "panels": [panel], "fading": False}
    wrong_tab = [frame for frame in frames if {key: frame[key] for key in shown} != shown]
    assert not wrong_tab, f"前回のタブのまま描いていない・中身がふわっと出た（{len(frames)} 回描いたうち）: {wrong_tab[:3]}"
    allowed = {last["first"]} if drawn_before_paint else {last["first"], *_NOT_DRAWN_YET}
    wrong_content = [frame for frame in frames if frame["first"] not in allowed]
    assert not wrong_content, f"中身が最初の描画から出ていない・違う中身が出た（{len(frames)} 回描いたうち）: {wrong_content[:3]}"
