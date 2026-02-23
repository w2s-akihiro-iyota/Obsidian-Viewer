// ==============================================
// history.js - 閲覧履歴管理（localStorage）
// ==============================================

const HISTORY_KEY = 'viewHistory';
const HISTORY_MAX = 30;

function initHistory() {
    // viewページ閲覧時に履歴を記録
    recordHistory();
    // サイドバーに履歴リストを描画
    renderHistoryList();
    // タブ切替イベント
    initSidebarTabs();
}

/**
 * 現在のviewページを履歴に記録
 */
function recordHistory() {
    const path = window.location.pathname;
    if (!path.startsWith('/view/')) return;

    const filePath = path.replace('/view/', '');
    const title = document.title.replace(' - Obsidian Viewer', '');

    let history = getHistory();

    // 同じパスの既存エントリを除去（最新に移動）
    history = history.filter(h => h.path !== filePath);

    // 先頭に追加
    history.unshift({
        path: filePath,
        title: title,
        timestamp: Date.now()
    });

    // 上限を超えたら古いものを削除
    if (history.length > HISTORY_MAX) {
        history = history.slice(0, HISTORY_MAX);
    }

    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
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
function renderHistoryList() {
    const container = document.getElementById('sidebar-history');
    if (!container) return;

    const history = getHistory();

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
 * サイドバータブ切替
 */
function initSidebarTabs() {
    const tabs = document.querySelectorAll('.sidebar-tab[data-panel]');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const panelId = tab.dataset.panel;

            // タブのactive切替
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // パネルのactive切替
            document.querySelectorAll('.sidebar-panel').forEach(p => p.classList.remove('active'));
            const panel = document.getElementById(panelId);
            if (panel) panel.classList.add('active');
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
