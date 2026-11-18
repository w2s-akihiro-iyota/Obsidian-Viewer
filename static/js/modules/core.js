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
 * URL に、外部の人の表示なら as=public を付ける（X-7・F-16）。
 * API（ツリー・検索・プレビュー・つながり）は外部の人と同じ中身（公開ノートだけ）に、
 * 記事ページへの移動は外部の人の表示のまま移れるようにする。
 * as=public はクエリに足し、?hl= と #見出し は残す（# の前に入る）
 * 'as' と 'public' は app/config.py の VIEW_AS_PARAM / VIEW_AS_PUBLIC と対応（F-17）
 */
function withViewAs(url) {
    if (!isPublicView()) return url;
    const parsed = new URL(url, window.location.origin);
    parsed.searchParams.set('as', 'public');
    return parsed.pathname + parsed.search + parsed.hash;
}

// --- モーダル（重なり・Esc・裏のスクロールの固定・ショートカットを止める） ---
// モーダルの一覧はこの 1 つだけ（開いているときは .active が付く）。モーダルを足したら、ここに足す。
// 次のことは、どれもこの一覧から決める（前はそれぞれが自分の一覧を持っていて、足し忘れると食い違った。Q-32）
//   - Esc で閉じるのは、開いているもののうちいちばん上の 1 つだけ（closeOnEscapeWhenTopmost。B-28）
//   - 1 つでも開いていれば、裏の本文のスクロールを止める（syncBackgroundScrollLock。B-24）
//   - 1 つでも開いていれば、? の一覧を開かず、記事ページの G などのショートカットを効かせない。
//     つながり・＋・ツリーの絞り込み欄の Esc も、モーダルに譲る（isAnyModalOpen）
// 並びは重なりの上からの順で、実際の重なり（z-index。同じ z-index なら DOM で後ろにあるほうが上）に合わせる
//   - 画像の拡大: 9999（content.css の .lightbox-overlay）。どのモーダルより上
//   - 検索: --z-quick-switcher（3200。variables.css）。Ctrl+K で、ようこそ・設定・ヘルプの上からも開くので、それらより上（B-29）
//   - ようこそ: 3100（tutorial.css の #welcome-modal）
//   - ? の一覧: --z-modal（3000。settings.css の .settings-modal）。同じ 3000 のヘルプ・設定より DOM で後ろ
//     （base.html の include の順: 検索 → ようこそ → ヘルプ → 設定 → 一覧）
//   - フォルダ選び: 設定の中に入れ子（_modal_settings.html）で、設定の中身より上（z-index: var(--z-dropdown)）。設定の上にだけ開く
//   - 設定: 3000（.settings-modal）。ヘルプより DOM で後ろ
//   - ヘルプ: 3000（tutorial.css の #help-modal）
const MODALS_TOP_FIRST = [
    '#lightbox-overlay',
    '#search-modal',
    '#welcome-modal',
    '#shortcut-sheet',
    '#dir-browser-modal',
    '#settings-modal',
    '#help-modal',
];

/**
 * 開いているモーダルのうち、いちばん上のもの（どれも開いていなければ null）
 */
function topmostOpenModal() {
    for (const selector of MODALS_TOP_FIRST) {
        const modal = document.querySelector(`${selector}.active`);
        if (modal) return modal;
    }
    return null;
}

/**
 * モーダルが 1 つでも開いているか。
 * 開いているあいだは、? の一覧を開かず、記事ページの G などのショートカットを効かせない。
 * モーダルの外の Esc の受け手（つながり・＋・ツリーの絞り込み欄）も、これを見てモーダルに譲る
 */
function isAnyModalOpen() {
    return topmostOpenModal() !== null;
}

/**
 * modal がいちばん上に開いているときだけ、Esc で close を呼ぶ（モーダルの Esc は、どれもこれで受ける）。
 * どれがいちばん上かを MODALS_TOP_FIRST の 1 か所で決めるのは、各モーダルが自分が開いているかだけを見て Esc を受けると、
 * 重なっているとき 1 回の Esc で下のモーダルまで閉じてしまうため（ヘルプの上で Ctrl+K で開いた検索を Esc で閉じると、ヘルプも閉じた。B-28）。
 * 閉じたら preventDefault し、同じ Esc の受け手のうち後から呼ばれるものは、defaultPrevented を見て何もしない。
 * そうしないと、上のモーダルが閉じたあとに呼ばれる受け手から見て、下のモーダルが「いちばん上」になり、続けて閉じてしまう
 */
function closeOnEscapeWhenTopmost(modal, close) {
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape' || e.defaultPrevented || topmostOpenModal() !== modal) return;
        e.preventDefault();
        close();
    });
}

/**
 * 本文のスクロールの固定（body.no-scroll）を、いま開いているモーダルに合わせる（画像の拡大も止める。X-11）。
 * 1 つでも開いていれば固定し、全部閉じたら外す。モーダルの .active を付けた・外したあとに必ず呼ぶ。
 * 付け外しをここ 1 か所で決めるのは、モーダルが重なることがあるため。
 * 閉じるモーダルが自分で外すと、まだ開いているモーダルの裏で本文が動いてしまう
 * （? の一覧の上で Ctrl+K を押すと、一覧が閉じて検索が残る。設定の上で開いた検索を閉じても、設定は残る。B-24）
 */
function syncBackgroundScrollLock() {
    document.body.classList.toggle('no-scroll', isAnyModalOpen());
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
