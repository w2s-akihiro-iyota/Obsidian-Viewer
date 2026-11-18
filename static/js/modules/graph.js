// ==============================================
// graph.js - 全体グラフ（/graph）
// 描画は graph-render.js の renderForceGraph。最初は全部の点が枠に収まる倍率で開き、
// ?focus=<slug> のときはそのノートを中央に寄せて色を付ける。配置は localStorage に覚える（Q-39）
// ==============================================

(function () {
    const canvas = document.getElementById('graph-canvas');
    if (!canvas) return;

    function showMessage(text) {
        const div = document.createElement('div');
        div.className = 'graph-message';
        div.textContent = text;
        canvas.replaceChildren(div);
    }

    if (typeof d3 === 'undefined') {
        showMessage('グラフを描くライブラリを読み込めませんでした。ネットワークの接続を確かめてください');
        return;
    }

    const focusSlug = new URLSearchParams(window.location.search).get('focus');

    fetch(withViewAs('/api/graph'))
        .then(r => r.json())
        .then(data => {
            if (!data.nodes.length) {
                showMessage('グラフに表示するノードがありません');
                return;
            }
            const focus = focusSlug ? data.nodes.find(n => n.slug === focusSlug) : null;
            const graph = renderForceGraph(canvas, data, {
                hideLabelsBelow: 0.5,   // 全体を収めた小さい倍率では、ラベルが重なって読めないので隠す
                // 配置を覚えて、点と線が変わっていなければ次は計算せずに描く（Q-39）。外部の人の表示は点が違うので別に覚える
                layoutKey: isPublicView() ? 'graphLayoutPublic' : 'graphLayout',
                nodeClass: d => (focus && d.id === focus.id ? 'is-focus' : ''),
            });
            const show = (duration) => {
                graph.zoomToFit();
                if (focus) graph.focusNode(focus.id, { minScale: 1.5, duration });
            };
            // 点は配置が落ち着いてから出る（graph-render.js）。枠に収めるのはそのあと
            graph.ready.then(() => {
                show(600);
                // 枠の大きさが変わったら（読みやすい幅の設定の反映・ウィンドウの大きさの変更）合わせ直す
                if (window.ResizeObserver) {
                    let size = `${canvas.clientWidth}x${canvas.clientHeight}`;
                    new ResizeObserver(() => {
                        const now = `${canvas.clientWidth}x${canvas.clientHeight}`;
                        if (now !== size) { size = now; show(0); }
                    }).observe(canvas);
                }
            });
        })
        .catch(() => showMessage('グラフのデータを読み込めませんでした'));
})();
