// ==============================================
// local-graph-panel.js - 記事ページの「つながり」のパネルの開閉
// 開く・閉じる、フォーカスの移動と戻し、Esc と G キー、パネルの外（スマホでは暗幕）を押したら閉じる
// 中身（深さ・読み込み・描画）は local-graph.js が onOpen で受け持つ
// 開くボタン（trigger）は setTrigger で差し替えられる（右上のボタンを 1 つにまとめたときに、まとめたボタンから開けるように）
// 閉じたときにフォーカスを戻す先は、既定では trigger。trigger が閉じると隠れる場所にあるとき（768px 以下の「＋」の中）は
// setTrigger の 2 つめの引数で、見えているボタン（「＋」）を渡す
// 開閉を知りたい側（768px 以下の「＋」。article-dial.js）は onOpenChange で登録する
// ==============================================

/**
 * @param {object} o
 * @param {HTMLElement} o.panel パネル（hidden で開閉する）
 * @param {HTMLElement|null} o.backdrop 暗幕（768px 以下で見える。パネルと一緒に開閉する）
 * @param {HTMLElement|null} o.closeButton ✕ ボタン
 * @param {HTMLElement|null} o.trigger 開くボタン（押すと開閉。aria-expanded を付け、閉じたらフォーカスを戻す）
 * @param {string} o.shortcutKey 開閉のキー（app/shortcuts.py の定義。テンプレートが data-shortcut-key で渡す）
 * @param {Function} o.onOpen 開いたときに呼ぶ
 * @returns {{open: Function, close: Function, isOpen: Function, setTrigger: Function, onOpenChange: Function}}
 */
function createLocalGraphPanel(o) {
    const { panel, backdrop, closeButton, onOpen } = o;
    const shortcutKey = (o.shortcutKey || '').toLowerCase();
    let trigger = null;
    let focusTarget = null;  // 閉じたときにフォーカスを戻す先（既定は trigger）
    const openChangeListeners = [];

    /**
     * 開閉したときに呼ぶ関数を登録する
     * @param {(open: boolean) => void} fn
     */
    function onOpenChange(fn) {
        openChangeListeners.push(fn);
    }

    const notifyOpenChange = (open) => openChangeListeners.forEach(fn => fn(open));

    const isOpen = () => !panel.hidden;

    function open() {
        if (isOpen()) return;
        panel.hidden = false;
        if (backdrop) backdrop.hidden = false;
        if (trigger) trigger.setAttribute('aria-expanded', 'true');
        panel.focus({ preventScroll: true });
        if (onOpen) onOpen();
        notifyOpenChange(true);
    }

    /**
     * @param {boolean} restoreFocus 開くボタンにフォーカスを戻すか（パネルの外を押したときは、押した先のフォーカスを奪わない）
     */
    function close(restoreFocus = true) {
        if (!isOpen()) return;
        const focusWasInside = panel.contains(document.activeElement);
        panel.hidden = true;
        if (backdrop) backdrop.hidden = true;
        if (trigger) trigger.setAttribute('aria-expanded', 'false');
        if (focusTarget && (restoreFocus || focusWasInside || document.activeElement === document.body)) {
            focusTarget.focus({ preventScroll: true });
        }
        notifyOpenChange(false);
    }

    const toggle = () => (isOpen() ? close() : open());

    /**
     * @param {HTMLElement|null} el 開くボタン（押すと開閉し、aria-expanded を付ける）
     * @param {HTMLElement|null} returnFocusTo 閉じたときにフォーカスを戻す先（省略すると el）
     */
    function setTrigger(el, returnFocusTo = el) {
        if (trigger) {
            trigger.removeEventListener('click', toggle);
            trigger.setAttribute('aria-expanded', 'false');
        }
        trigger = el || null;
        focusTarget = returnFocusTo || trigger;
        if (trigger) {
            trigger.addEventListener('click', toggle);
            trigger.setAttribute('aria-expanded', String(isOpen()));
        }
    }

    setTrigger(o.trigger);
    if (closeButton) closeButton.addEventListener('click', () => close());

    // パネルの外（スマホでは暗幕）を押したら閉じる
    document.addEventListener('click', (e) => {
        if (!isOpen() || !(e.target instanceof Node)) return;
        if (panel.contains(e.target) || (trigger && trigger.contains(e.target))) return;
        close(false);
    });

    // Esc と G。キャプチャで先に受け、ほかのモーダル（ヘルプ・チートシート・クイックスイッチャー・画像の拡大）が
    // 開いているときは何もしない（Esc はそちらが閉じる）
    document.addEventListener('keydown', (e) => {
        if (isShortcutModalOpen()) return;
        if (e.key === 'Escape') {
            if (!isOpen()) return;
            // 開いているつながりだけを閉じる（ツリーの絞り込み欄などの Esc は動かさない）
            e.preventDefault();
            e.stopPropagation();
            close();
            return;
        }
        if (!shortcutKey || e.key.toLowerCase() !== shortcutKey || e.shiftKey || !isShortcutKey(e)) return;
        e.preventDefault();
        if (e.repeat) return;   // 押しっぱなしで開閉を繰り返さない
        toggle();
    }, true);

    return { open, close, isOpen, setTrigger, onOpenChange };
}
