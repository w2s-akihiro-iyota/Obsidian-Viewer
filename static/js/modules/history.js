// ==============================================
// history.js - 閲覧履歴（localStorage）とサイドバーのタブ
// ==============================================
// base.html の head で、defer を付けずに読む（B-32）。本文を読みながら、サイドバーを前回のタブと閲覧履歴の一覧のまま組み立てる
// （buildSidebarWhileParsing）。defer で読んで DOMContentLoaded を待つと、本文を読み終えたところの最初の描画に間に合わず、
// 「ファイル」タブで一度描いてから前回のタブに切り替わってちらつく。
// トップレベルでは、core.js など defer で読むファイルの関数を使わない（まだ読み込まれていない）。initHistory は main.js が呼ぶ

const HISTORY_KEY = 'viewHistory';
const HISTORY_MAX = 30;
const SIDEBAR_TAB_KEY = 'sidebarTab';
const SIDEBAR_DEFAULT_TAB = 'sidebar-files';

buildSidebarWhileParsing();

/**
 * 本文を読みながら（MutationObserver）、サイドバーのタブとパネルが現れたらすぐ前回のタブを選び、
 * 閲覧履歴のパネルが現れたら一覧を描く。MutationObserver の知らせは、読んだところを描くより先に届くので、
 * サイドバーは最初の描画から前回のタブと一覧のまま出る。
 * 閲覧履歴のパネル（base.html では最後のパネル。中身は空にしておく）が現れたら終わる
 */
function buildSidebarWhileParsing() {
    const saved = localStorage.getItem(SIDEBAR_TAB_KEY);
    const observer = new MutationObserver(() => {
        // タブとパネルは読んだところまでしか無いので、知らせのたびに選び直す
        if (saved) showSidebarTab(saved);
        if (!document.getElementById('sidebar-history')) return;
        observer.disconnect();
        // 覚えていたタブがもう無い（名前の変わった古い値）ときは、既定のタブにする
        if (!document.querySelector('.sidebar-tab.active')) showSidebarTab(SIDEBAR_DEFAULT_TAB);
        // 先読み（F-15）中も描く（開いたらすぐ出す）。覚えるのは画面に出てから（initHistory）
        renderHistoryList(historyAfterOpening());
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    // サイドバーの無いページでも、読み終えたら見張りをやめる（そのあとの DOM の変化のたびに呼ばれ続けないように）
    document.addEventListener('DOMContentLoaded', () => observer.disconnect(), { once: true });
}

function initHistory() {
    // 開いたページを閲覧履歴に覚える。先読み（F-15）中は覚えない（マウスを乗せただけのノートを履歴に載せない・外さない）。
    // 一覧は本文を読みながら描いてあるが、先読みしてから開くまでに、ほかのタブで履歴が変わっていることがあるので描き直す
    // （先読みでなければ、描いてある一覧と同じ中身になる）
    whenPageShown(() => {
        const history = historyAfterOpening();
        saveHistory(history);
        renderHistoryList(history);
    });
    initSidebarTabs();
}

/**
 * いま開いているページを反映した閲覧履歴を返す（B-19。読むだけ。覚えるのは saveHistory）。どちらのページかは body の印で見分ける
 * - 記事ページ（page-view）: 先頭に載せる。同じノートの前の記録は消して先頭へ移す
 * - ノートが見つからない画面（is-note-missing。/view/... の 404。error.html）: そのノートを外す
 *   （404 の画面は載せない。前に載せたあとで消えた・名前が変わったノートも、開いて 404 になった時点で消える）
 * - そのほか（ほかのエラー画面・一覧など）: そのまま
 */
function historyAfterOpening() {
    const history = getHistory();
    const path = window.location.pathname;
    if (!path.startsWith('/view/')) return history;
    const opened = document.body.classList.contains('page-view');
    if (!opened && !document.body.classList.contains('is-note-missing')) return history;

    const filePath = path.slice('/view/'.length);
    const others = history.filter(h => h.path !== filePath);
    if (!opened) return others;
    const current = {
        path: filePath,
        title: document.title.replace(' - Obsidian Viewer', ''),
        timestamp: Date.now()
    };
    return [current, ...others].slice(0, HISTORY_MAX);
}

/**
 * 閲覧履歴を覚える。変わっていなければ書かない
 */
function saveHistory(history) {
    const text = JSON.stringify(history);
    if (text !== localStorage.getItem(HISTORY_KEY)) localStorage.setItem(HISTORY_KEY, text);
}

/**
 * 履歴を取得
 */
function getHistory() {
    try {
        return JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
    } catch {
        return [];
    }
}

/**
 * サイドバーの履歴パネルに描画
 */
function renderHistoryList(history) {
    const container = document.getElementById('sidebar-history');
    if (!container) return;

    if (history.length === 0) {
        container.innerHTML = '<div class="history-empty">閲覧履歴はありません</div>';
        return;
    }

    const list = document.createElement('ul');
    list.className = 'history-list';

    history.forEach(item => {
        const li = document.createElement('li');
        li.className = 'history-item';

        const link = document.createElement('a');
        link.href = `/view/${item.path}`;
        link.className = 'history-link';

        const titleEl = document.createElement('span');
        titleEl.className = 'history-title';
        titleEl.textContent = item.title;

        const timeEl = document.createElement('span');
        timeEl.className = 'history-time';
        timeEl.textContent = formatRelativeTime(item.timestamp);

        link.appendChild(titleEl);
        link.appendChild(timeEl);
        li.appendChild(link);
        list.appendChild(li);
    });

    container.innerHTML = '';
    container.appendChild(list);
}

/**
 * 相対時間表示
 */
function formatRelativeTime(timestamp) {
    const now = Date.now();
    const diff = now - timestamp;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return 'たった今';
    if (minutes < 60) return `${minutes}分前`;
    if (hours < 24) return `${hours}時間前`;
    if (days < 30) return `${days}日前`;
    return new Date(timestamp).toLocaleDateString('ja-JP');
}

/**
 * サイドバーのタブを選ぶ（タブとパネルの .active を付け替える）。本文を読んでいる途中でも呼べる（いまあるものだけ付け替える）。
 * fade: パネルの中身をふわっと出す。タブを押したときだけにする（ページを開くたびに出すと、サイドバーを描き直したように見える。B-32）
 */
function showSidebarTab(panelId, { fade = false } = {}) {
    document.querySelectorAll('.sidebar-tab[data-panel]').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.panel === panelId);
    });
    document.querySelectorAll('.sidebar-panel').forEach(panel => {
        const active = panel.id === panelId;
        panel.classList.toggle('active', active);
        panel.classList.toggle('fade-in', active && fade);
    });
}

/**
 * サイドバータブ切替（前回選んでいたタブは、本文を読みながら選んである。buildSidebarWhileParsing）
 */
function initSidebarTabs() {
    document.querySelectorAll('.sidebar-tab[data-panel]').forEach(tab => {
        tab.addEventListener('click', () => {
            showSidebarTab(tab.dataset.panel, { fade: true });
            localStorage.setItem(SIDEBAR_TAB_KEY, tab.dataset.panel);
        });
    });

    // Activity barの履歴ボタン
    const historyBtn = document.getElementById('activity-history-btn');
    if (historyBtn) {
        historyBtn.addEventListener('click', () => {
            // サイドバーを開く
            const sidebar = document.getElementById('sidebar');
            if (sidebar && document.documentElement.classList.contains('sidebar-collapsed')) {
                document.documentElement.classList.remove('sidebar-collapsed');
                localStorage.setItem('sidebarCollapsed', 'false');
            }

            // Historyタブを選択
            const historyTab = document.querySelector('.sidebar-tab[data-panel="sidebar-history"]');
            if (historyTab) historyTab.click();
        });
    }
}
