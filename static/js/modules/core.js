// ==============================================
// core.js - Shared constants, state, and utilities
// ==============================================

// 検索欄の打鍵が止まってから問い合わせるまでの待ち（Q-22）。サーバーは 10〜60ms で返すので、待ちを短くして候補を早く出す
const DEBOUNCE_DELAY = 120;
const SCROLL_SHOW_THRESHOLD = 300;
const SIDEBAR_MIN_WIDTH = 200;
const SIDEBAR_MAX_WIDTH = 600;
const TOAST_DURATION = 3000;
// 押せるボタン（「内訳を見る」など）が付いたトーストは、押す間があるよう長めに出す
const TOAST_ACTION_DURATION = 8000;
const COPY_FEEDBACK_DURATION = 2000;

let MESSAGES = { errors: {}, warnings: {}, system: {} };
let tutorialMode = false;
let tutorialStep = 0;

async function loadMessages() {
    try {
        const response = await fetch('/api/messages');
        if (response.ok) {
            MESSAGES = await response.json();
            console.log("Messages loaded successfully");
        }
    } catch (err) {
        console.error("Failed to load messages", err);
    }
}

/**
 * ページが実際に画面に出たときに fn を呼ぶ（先読みでなければすぐ呼ぶ）。
 * 先読み（F-15。base.html の speculationrules）では、まだ開いていないページの JS も裏で動く。
 * ページを開いたときに動く処理のうち、次のものはここを通して先読み中に動かさない
 *   - localStorage・sessionStorage への書き込み（閲覧履歴・サイドバーのスクロール位置など）
 *   - 一度きりのフラグの読み捨てと、その判定（初回のお祝い・同期完了のトースト・ようこそモーダル）
 *   - サーバーへの書き込み（POST など）
 * 読むだけの取得（GET の fetch）と、画面を組み立てるだけの処理は通さなくてよい（先に済ませておくのが先読みの狙い）
 */
function whenPageShown(fn) {
    if (document.prerendering) {
        document.addEventListener('prerenderingchange', () => fn(), { once: true });
    } else {
        fn();
    }
}

// 記事ページの URL。スラッグの区切り（/）は残し、区切りの間をエンコードする（# ? % で移動先が壊れないように）
function viewUrl(slug) {
    return '/view/' + String(slug).split('/').map(encodeURIComponent).join('/');
}

/**
 * 管理者の「外部の人の表示」（?as=public）のページか（base.html が body に data-view-as="public" を付ける）。
 * 外部の人のページには付かない（API がもともと公開ノートだけを返す）
 */
function isPublicView() {
    return document.body.dataset.viewAs === 'public';
}

/**
 * API の URL に、外部の人の表示なら as=public を付ける（X-7）。
 * ツリー・検索・プレビュー・つながりを、外部の人と同じ中身（公開ノートだけ）にする
 */
function withViewAs(url) {
    if (!isPublicView()) return url;
    return url + (url.includes('?') ? '&' : '?') + 'as=public';
}

// --- Toast Notification System ---
/**
 * トーストを出す
 * @param {string} message
 * @param {string} type - info / success / error / warning
 * @param {{label: string, onClick: Function}|null} action - 付けるとメッセージの右にボタンを出す。押すとトーストを閉じる
 */
function showToast(message, type = 'info', action = null) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    // Icon based on type
    let icon = '';
    if (type === 'success') icon = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>';
    else if (type === 'error') icon = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>';
    else if (type === 'warning') icon = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>';

    toast.innerHTML = `${icon}<span>${message}</span>`;
    if (action) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'toast-action';
        btn.textContent = action.label;
        btn.addEventListener('click', () => {
            toast.remove();
            action.onClick();
        });
        toast.appendChild(btn);
    }

    container.appendChild(toast);

    // Animate in
    requestAnimationFrame(() => toast.classList.add('show'));

    // Remove after duration
    setTimeout(() => {
        toast.classList.remove('show');
        toast.addEventListener('transitionend', () => toast.remove());
    }, action ? TOAST_ACTION_DURATION : TOAST_DURATION);
}

// --- Clipboard Utility ---
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
    } catch (err) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        try {
            document.execCommand('copy');
        } catch (fallbackErr) {
            throw fallbackErr;
        } finally {
            document.body.removeChild(textarea);
        }
    }
}

// --- Celebration Animation ---
function showCelebration() {
    const overlay = document.createElement('div');
    overlay.className = 'celebration-overlay';

    // 紙吹雪パーティクル
    const colors = ['#7b61ff', '#ff6b6b', '#feca57', '#48dbfb', '#ff9ff3', '#54a0ff', '#5f27cd', '#01a3a4'];
    const shapes = ['square', 'circle', 'strip'];
    for (let i = 0; i < 60; i++) {
        const piece = document.createElement('div');
        const shape = shapes[Math.floor(Math.random() * shapes.length)];
        piece.className = `confetti-piece confetti-${shape}`;
        piece.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
        piece.style.left = Math.random() * 100 + '%';
        piece.style.animationDelay = Math.random() * 0.8 + 's';
        piece.style.animationDuration = (2 + Math.random() * 2) + 's';
        overlay.appendChild(piece);
    }

    // お祝いメッセージ
    const msg = document.createElement('div');
    msg.className = 'celebration-message';
    msg.innerHTML = `
        <div class="celebration-icon">&#127881;</div>
        <div class="celebration-title">セットアップ完了！</div>
        <div class="celebration-subtitle">ファイルの同期が正常に完了しました。<br>さっそくファイルを閲覧してみましょう。</div>
    `;
    overlay.appendChild(msg);

    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('active'));

    // クリックまたは5秒後にフェードアウト
    let removed = false;
    const remove = () => {
        if (removed) return;
        removed = true;
        overlay.classList.add('fade-out');
        overlay.addEventListener('transitionend', () => overlay.remove(), { once: true });
        setTimeout(() => overlay.remove(), 600);
    };

    overlay.addEventListener('click', remove);
    setTimeout(remove, 5000);
}
