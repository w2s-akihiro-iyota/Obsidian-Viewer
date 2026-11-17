// ==============================================
// shortcuts.js - ? で開くショートカット一覧（チートシート。F-9）
// 中身は templates/partials/_modal_shortcuts.html がサーバー側で描く（定義は app/shortcuts.py）
// ==============================================

// これらが開いているあいだは ? で開かない（ほかのモーダルの操作を邪魔しない）
const SHORTCUT_SHEET_BLOCKERS = '#help-modal.active, #search-modal.active, #settings-modal.active, #welcome-modal.active, #lightbox-overlay.active';

function initShortcutSheet() {
    const modal = document.getElementById('shortcut-sheet');
    if (!modal) return;

    const sheet = modal.querySelector('.shortcut-sheet');
    const body = modal.querySelector('.shortcut-sheet-body');
    const helpLink = document.getElementById('shortcut-sheet-help');
    // サーバーが並べた順（いまの画面に合わせた順）。開くたびにここから並べ直す
    const defaultOrder = Array.from(body.querySelectorAll('.shortcut-sheet-group'));
    let returnFocus = null;

    const isOpen = () => modal.classList.contains('active');

    const open = () => {
        returnFocus = document.activeElement;
        arrangeGroups(returnFocus);
        modal.classList.add('active');
        syncBackgroundScrollLock();
        body.scrollTop = 0;
        // Esc を受けられるように、開いたシートへフォーカスを移す
        sheet.focus({ preventScroll: true });
    };

    const close = ({ restoreFocus = true } = {}) => {
        modal.classList.remove('active');
        // Ctrl+K で検索に譲ったときは、検索が開いているので固定のまま（B-24）
        syncBackgroundScrollLock();
        if (restoreFocus) restoreFocusAfterSheet(returnFocus);
        returnFocus = null;
    };

    /**
     * フォーカスのあった場所で使えるグループを先頭に出す（ほかはサーバーが並べた順のまま）
     */
    function arrangeGroups(focused) {
        const place = shortcutPlaceOf(focused);
        const first = defaultOrder.filter(section => groupUsableAt(section, place));
        const rest = defaultOrder.filter(section => !first.includes(section));
        [...first, ...rest].forEach(section => body.appendChild(section));
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && isOpen()) {
            e.preventDefault();
            close();
            return;
        }
        // 開いたまま Ctrl+K を押したら、クイックスイッチャーに譲る（下に重ならないように閉じる）
        if (isOpen() && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
            close({ restoreFocus: false });
            return;
        }
        if (e.key !== '?' || !isShortcutKey(e)) return;
        if (isOpen()) {
            e.preventDefault();
            close();
            return;
        }
        if (document.querySelector(SHORTCUT_SHEET_BLOCKERS)) return;
        e.preventDefault();
        open();
    });

    // 背景（シートの外）を押したら閉じる
    modal.addEventListener('click', (e) => {
        if (e.target === modal) close();
    });

    // 「すべてのショートカット → ヘルプ」: ヘルプをショートカットタブで開く
    if (helpLink) {
        helpLink.addEventListener('click', () => {
            close({ restoreFocus: false });
            openHelpModal('keys');
        });
    }
}

/**
 * 一覧を閉じたら、開く前にフォーカスのあった場所へ戻す（ツリーなどから開いたなら、続けて操作できるように）。
 * その場所が隠れていて戻せない（768px 以下の「＋」の中から開くと、フォーカスが一覧へ移った時点で「＋」がしまう。B-26）なら、
 * 隠した入れ物が data-focus-fallback に書いた要素（id。「＋」の開閉ボタン）へ戻す。body に落とさない
 * 戻せたかは、見えているかを調べる代わりに、実際にフォーカスが移ったかで見る（隠れた・押せない・inert のどれでも外れる）
 */
function restoreFocusAfterSheet(el) {
    if (!el || !document.contains(el)) return;
    el.focus({ preventScroll: true });
    if (document.activeElement === el) return;
    const holder = el.closest('[data-focus-fallback]');
    const fallback = holder && document.getElementById(holder.dataset.focusFallback);
    if (fallback) fallback.focus({ preventScroll: true });
}

/**
 * 要素のある「フォーカスの場所」の id（data-shortcut-place。無ければ null）
 * 場所の id は app/shortcuts.py の FOCUS_* で、テンプレートが目印として付ける
 */
function shortcutPlaceOf(el) {
    if (!(el instanceof Element)) return null;
    const holder = el.closest('[data-shortcut-place]');
    return holder ? holder.dataset.shortcutPlace : null;
}

/**
 * グループ（data-contexts を持つ要素）が、その場所で使えるか
 */
function groupUsableAt(groupEl, place) {
    return Boolean(place) && (groupEl.dataset.contexts || '').split(' ').includes(place);
}

// 文字を打たない input（押す・選ぶだけ）の type。これにフォーカスがあっても 1 文字のショートカットは効かせる
// （つながりの歩数のラジオを押したあとも ? と G が効くように。B-25）
const NON_TYPING_INPUT_TYPES = new Set(['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color', 'file', 'image']);

/**
 * 1 文字のキー（? や記事ページの G）をショートカットとして扱ってよいか
 * 文字を打っている場所（文字を打つ input・textarea・contenteditable・select）、日本語の変換中、
 * Ctrl / ⌘ / Alt との組み合わせでは、文字入力やほかの操作に譲る
 */
function isShortcutKey(e) {
    if (e.isComposing || e.keyCode === 229) return false;
    if (e.ctrlKey || e.metaKey || e.altKey) return false;
    const target = e.target;
    if (!(target instanceof Element)) return true;
    if (target.isContentEditable) return false;
    if (target instanceof HTMLInputElement) return NON_TYPING_INPUT_TYPES.has(target.type);
    return !target.closest('textarea, select, [contenteditable]:not([contenteditable="false"])');
}

/**
 * モーダル（ヘルプ・ショートカット一覧・クイックスイッチャー・設定・ようこそ・画像の拡大）が開いているか
 * 開いているあいだは、記事ページの G などのショートカットを効かせず、Esc もそちらに譲る
 */
function isShortcutModalOpen() {
    return Boolean(document.querySelector(`${SHORTCUT_SHEET_BLOCKERS}, #shortcut-sheet.active`));
}
