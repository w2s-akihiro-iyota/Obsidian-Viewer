/**
 * ダッシュボード
 * - 「手入れが必要なノート」（F-6）: カードを押すと、その下に該当ノートの表を開く。もう一度押すと閉じる。開く表は 1 つだけ
 * - ヒートマップ: 横にスクロールする幅（スマホ）では、最近の週が見えるよう右端から表示する
 */
(function () {
    const cards = Array.from(document.querySelectorAll('.health-card[aria-controls]'));

    const setOpen = (card, open) => {
        const panel = document.getElementById(card.getAttribute('aria-controls'));
        if (!panel) return;
        panel.hidden = !open;
        card.setAttribute('aria-expanded', String(open));
    };

    cards.forEach(card => {
        card.addEventListener('click', () => {
            const open = card.getAttribute('aria-expanded') !== 'true';
            cards.forEach(other => setOpen(other, other === card && open));
        });
    });

    const heatmapScroll = document.querySelector('.heatmap-scroll');
    if (heatmapScroll) {
        heatmapScroll.scrollLeft = heatmapScroll.scrollWidth;
    }
})();
