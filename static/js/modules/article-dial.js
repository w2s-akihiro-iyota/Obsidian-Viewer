// ==============================================
// article-dial.js - 768px 以下の記事ページの右上の「＋」（つながり・メニューをまとめたボタン）の開閉
// 押すと「つながり」と「メニュー（⋮）」を縦に出す。閉じるのは「×」・暗幕（外側）・Esc
// 「メニュー」の中身は記事ヘッダーの ⋮（.page-menu-container）をそのまま移して使う（開閉は main.js / search.js のまま）。
// PC（769px 以上）では ⋮ を記事ヘッダーに戻し、「＋」は CSS で出さない（layout.css）
// つながりの開閉は local-graph-panel.js。768px 以下では閉じたときのフォーカスの戻し先を「＋」にする（setTrigger）
// 準備（⋮ の移動）を終えたら <html> に .article-dial-ready を付ける。CSS はこれが付いたときだけ「＋」にまとめる
// （このファイルが読めない・途中で止まったときは、記事ヘッダーの右の ⋮ と外部の人の表示がそのまま見える）
// ==============================================

// CSS（layout.css・graph.css）の 768px 以下と同じ境目
const ARTICLE_DIAL_MEDIA = '(max-width: 768px)';
// 準備ができたら <html> に付けるクラス（layout.css）
const ARTICLE_DIAL_READY_CLASS = 'article-dial-ready';

(function () {
    const dial = document.getElementById('article-dial');
    const toggle = document.getElementById('article-dial-toggle');
    if (!dial || !toggle) return;

    const items = document.getElementById('article-dial-items');
    const menuSlot = document.getElementById('article-dial-menu');
    const backdrop = dial.querySelector('.article-dial-backdrop');
    const graphToggle = document.getElementById('local-graph-toggle');
    const pageMenu = document.querySelector('.page-menu-container');
    // ⋮ を PC に戻すときの元の場所
    const pageMenuHome = pageMenu ? { parent: pageMenu.parentElement, next: pageMenu.nextSibling } : null;
    const media = window.matchMedia(ARTICLE_DIAL_MEDIA);

    const isOpen = () => dial.classList.contains('is-open');

    function closePageMenu() {
        const dropdown = document.getElementById('page-menu-dropdown');
        if (dropdown) dropdown.classList.remove('show');
        document.getElementById('page-menu-btn')?.setAttribute('aria-expanded', 'false');
    }

    function open() {
        if (isOpen()) return;
        dial.classList.add('is-open');
        toggle.setAttribute('aria-expanded', 'true');
        const first = items.querySelector('button');
        if (first) first.focus({ preventScroll: true });
    }

    /**
     * @param {boolean} restoreFocus 「＋」にフォーカスを戻すか（つながりを開いたときは、つながりのシートにフォーカスを渡すので戻さない）
     */
    function close(restoreFocus = true) {
        if (!isOpen()) return;
        const focusWasInside = dial.contains(document.activeElement);
        dial.classList.remove('is-open');
        toggle.setAttribute('aria-expanded', 'false');
        closePageMenu();
        if (restoreFocus && focusWasInside) toggle.focus({ preventScroll: true });
    }

    toggle.addEventListener('click', () => (isOpen() ? close() : open()));
    if (backdrop) backdrop.addEventListener('click', () => close());

    // メニューの項目（編集・URL をコピー・PDF で出力）を選んだら、「＋」もしまう
    items.addEventListener('click', (e) => {
        if (e.target instanceof Element && e.target.closest('.menu-option')) close(false);
    });

    // キーボードで「＋」の外へ出たら閉じる（フォーカスは奪わない）
    dial.addEventListener('focusout', (e) => {
        if (isOpen() && e.relatedTarget instanceof Node && !dial.contains(e.relatedTarget)) close(false);
    });

    // 「＋」の外を押したら閉じる（ヘッダーのボタンなど。暗幕より上にあるもの）
    document.addEventListener('click', (e) => {
        if (!isOpen() || !(e.target instanceof Node) || dial.contains(e.target)) return;
        close(false);
    });

    // Esc: つながりのシート（local-graph-panel.js がキャプチャで先に受ける）や、ほかのモーダルが開いているときはそちらに譲る
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape' || !isOpen() || e.defaultPrevented || isShortcutModalOpen()) return;
        e.preventDefault();
        close();
    });

    // つながりが開いたら（「つながり」のボタンでも G キーでも）「＋」はしまう
    if (window.localGraphPanel) {
        window.localGraphPanel.onOpenChange((open) => {
            if (open) close(false);
        });
    }

    /**
     * 画面の幅に合わせて、⋮ の置き場所と、つながりを閉じたときのフォーカスの戻し先を決める
     */
    function arrange() {
        const narrow = media.matches;
        if (!narrow) close(false);
        if (pageMenu && menuSlot && pageMenuHome) {
            closePageMenu();
            if (narrow) menuSlot.appendChild(pageMenu);
            else pageMenuHome.parent.insertBefore(pageMenu, pageMenuHome.next);
        }
        // ⋮ を移し終えてから付ける（これより前に止まったら、今までの右上のボタンのまま）
        document.documentElement.classList.add(ARTICLE_DIAL_READY_CLASS);
        if (window.localGraphPanel && graphToggle) {
            window.localGraphPanel.setTrigger(graphToggle, narrow ? toggle : graphToggle);
        }
    }

    arrange();
    media.addEventListener('change', arrange);
})();
