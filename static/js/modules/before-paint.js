// ==============================================
// before-paint.js - 描く前に <html> へ表示の状態とコードの配色を付ける
// ==============================================
// base.html の head で、defer を付けずに読む（本文を描く前に走らせる。後から付けると、既定の見た目で一度描いてから変わってちらつく）。
// #highlight-theme の <link> より後ろに置くこと（その <link> の href を差し替える）。
// 前は base.html にインラインで書いていたが、CSP（S-10）でインラインの script は動かないので、外のファイルにした
(function () {
    const html = document.documentElement;

    // テーマ
    html.setAttribute('data-theme', localStorage.getItem('theme') || 'dark');

    // サイドバーの開閉（既定は畳む）
    const savedSidebarState = localStorage.getItem('sidebarCollapsed');
    const isCollapsed = savedSidebarState === null ? true : savedSidebarState === 'true';
    if (isCollapsed) {
        html.classList.add('sidebar-collapsed');
    }

    // サイドバーの幅
    const savedWidth = localStorage.getItem('sidebarWidth');
    if (savedWidth && window.innerWidth > 768) {
        html.style.setProperty('--sidebar-width', savedWidth + 'px');
    }

    // 読みやすい幅と文字サイズ（後から付けると、全幅で一度描いてから縮んでかくつく）。
    // 既定値と付け替えは settings.js と同じ
    if (localStorage.getItem('readableWidth') !== 'false') {
        html.classList.add('readable-width');
    }
    html.classList.add('font-' + (localStorage.getItem('fontSize') || 'medium'));

    // 記事のプロパティを閉じて覚えているときも、閉じた見た目にする（開いてから閉じるちらつきを防ぐ）。
    // 外すのと、開閉の保存は main.js
    if (localStorage.getItem('propertiesOpen') === 'false') {
        html.classList.add('properties-collapsed');
    }

    // コードの配色（highlight.js のテーマ）。設定の codeTheme で決め、画面テーマ（dark/light など）とは連動しない（既定 github-dark）。
    // テーマ名とファイルの対応は window.codeThemeHref に 1 か所だけ置き、設定での切り替え（main.js の updateHighlightTheme）も使う
    const files = {
        'github-dark': 'github-dark.min.css',
        'github': 'github.min.css',
        'dracula': 'dracula.min.css',
        'nord': 'nord.min.css',
        'tokyo-night-dark': 'tokyo-night-dark.min.css',
        'atom-one-dark': 'atom-one-dark.min.css'
    };
    window.codeThemeHref = function (name) {
        return '/static/css/themes/' + (files[name] || files['github-dark']);
    };
    const link = document.getElementById('highlight-theme');
    const saved = localStorage.getItem('codeTheme');
    if (link && saved) link.href = window.codeThemeHref(saved);
})();
