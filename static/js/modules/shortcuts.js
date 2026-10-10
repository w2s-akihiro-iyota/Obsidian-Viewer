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
        document.body.classList.add('no-scroll');
        body.scrollTop = 0;
        // Esc を受けられるように、開いたシートへフォーカスを移す
        sheet.focus({ preventScroll: true });
    };

    const close = ({ restoreFocus = true } = {}) => {
        modal.classList.remove('active');
        document.body.classList.remove('no-scroll');
        // ツリーなどから開いたなら、閉じたらその場所に戻って続けて操作できるように
        if (restoreFocus && returnFocus && document.contains(returnFocus)) {
            returnFocus.focus({ preventScroll: true });
        }
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
        if (e.key !== '?' || !isShortcutSheetKey(e)) return;
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

/**
 * ? をショートカット一覧のキーとして扱ってよいか
 * 文字を打っている場所（入力欄・textarea・contenteditable・select）、日本語の変換中、
 * Ctrl / ⌘ / Alt との組み合わせでは、文字入力やほかの操作に譲る
 */
function isShortcutSheetKey(e) {
    if (e.isComposing || e.keyCode === 229) return false;
    if (e.ctrlKey || e.metaKey || e.altKey) return false;
    const target = e.target;
    if (!(target instanceof Element)) return true;
    if (target.isContentEditable) return false;
    return !target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"])');
}
