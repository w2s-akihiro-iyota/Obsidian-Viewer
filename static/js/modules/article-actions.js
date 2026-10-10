// ==============================================
// article-actions.js - 記事ページの右上のアクション置き場（.article-actions）の置き場所を決める
// 本文の列の外側（右）に置ける余白があれば is-outside を付け、無ければ外す（記事ヘッダーの行の右に余白を取る。layout.css）
// 決め終わったら is-placed を付けて見せる（決まるまでは隠し、1 フレームだけ位置が動くのを見せない）
// ==============================================

(function () {
    const block = document.getElementById('article-actions');
    if (!block) return;

    // 外側に置くときに画面の右端に残す余白（CSS の --article-actions-edge-margin。二重に持たない）
    function edgeMargin() {
        return parseFloat(getComputedStyle(block).getPropertyValue('--article-actions-edge-margin')) || 0;
    }

    function place() {
        block.classList.add('is-outside');
        const right = Math.max(...[...block.children].map(child => child.getBoundingClientRect().right));
        if (right > document.documentElement.clientWidth - edgeMargin()) block.classList.remove('is-outside');
        block.classList.add('is-placed');
    }

    let frame = 0;
    function schedule() {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(place);
    }

    place();
    window.addEventListener('resize', schedule);
    // 本文の幅（読みやすい幅の設定）やサイドバーの開閉で、本文の列の位置が変わる
    if (window.ResizeObserver) {
        const observer = new ResizeObserver(schedule);
        observer.observe(block.parentElement);
        const sidebar = document.getElementById('sidebar');
        if (sidebar) observer.observe(sidebar);
    }
    if (window.MutationObserver) {
        const observer = new MutationObserver(schedule);
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
        observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    }
})();
