// ==============================================
// graph-render.js - D3.js のフォースレイアウトでグラフを描く
// 全体グラフ（graph.js）と記事ページのローカルグラフ（local-graph.js）で共通
// 色は CSS（graph.css の .graph-node 等）が CSS 変数で塗るので、テーマを切り替えても追従する
// ==============================================

// フォースレイアウトが落ち着くまでの tick 数（d3 の既定 alphaMin・alphaDecay で約 300）
const GRAPH_SETTLE_TICKS = 300;
// 拡大縮小できる倍率の範囲（枠に収めるときの最小倍率の既定値もこれ）
const GRAPH_MIN_ZOOM = 0.05;
const GRAPH_MAX_ZOOM = 4;

/**
 * container の中に SVG のグラフを描く
 * @param {HTMLElement} container 描画先（中身は置き換える）
 * @param {{nodes: Array, links: Array}} data /api/graph の JSON
 * @param {object} options 下の defaults を参照
 * @returns {{svg, node, label, zoomToFit: Function, focusNode: Function, destroy: Function}}
 *   destroy は描き直す前に呼ぶ（シミュレーションを止め、container を空にする）
 */
function renderForceGraph(container, data, options = {}) {
    const o = Object.assign({
        linkDistance: 100,
        charge: -200,
        collide: 30,
        gravity: 0.05,              // 中央へ引き寄せる強さ（つながりの無い点が遠くへ散らばらないように。0 で無し）
        hideLabelsBelow: 0,         // 倍率がこれより小さいときはラベルを隠す（0 なら常に出す）
        labelPlacement: 'right',    // 'right' | 'below'
        labelMaxChars: 0,           // ラベルをこの文字数で切って … を付ける（0 なら切らない。全文は点のツールチップ）
        minFitScale: GRAPH_MIN_ZOOM, // 枠に収めるときの最小倍率
        zoomable: true,             // ホイール・ドラッグで拡大縮小・移動できるか
        maxFitScale: 1.5,           // 枠に収めるときの最大倍率（点が少ないときに大きくしすぎない）
        fitPadding: 24,
        hover: true,                // ホバーでつながった点だけを強調する
        nodeRadius: null,           // (d, linkCount) => 半径。省略時はリンク数で決める
        nodeClass: () => '',        // (d) => 追加のクラス
        ariaLabel: 'ノートのつながりのグラフ',
        onNodeClick: (d) => { window.location.href = `/view/${d.slug}`; },
    }, options);

    container.innerHTML = '';
    const width = container.clientWidth;
    const height = container.clientHeight || Math.max(600, window.innerHeight - 120);

    const svg = d3.select(container)
        .append('svg')
        .attr('class', 'graph-svg')
        .attr('width', width)
        .attr('height', height)
        .attr('role', 'img')
        .attr('aria-label', o.ariaLabel);
    const g = svg.append('g');

    const zoom = d3.zoom()
        .scaleExtent([GRAPH_MIN_ZOOM, GRAPH_MAX_ZOOM])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
            svg.classed('is-labels-hidden', event.transform.k < o.hideLabelsBelow);
        });
    if (o.zoomable) svg.call(zoom);

    const idOf = (end) => (typeof end === 'object' ? end.id : end);

    // リンク数でノードサイズを決定
    const linkCount = {};
    data.links.forEach(l => {
        linkCount[idOf(l.source)] = (linkCount[idOf(l.source)] || 0) + 1;
        linkCount[idOf(l.target)] = (linkCount[idOf(l.target)] || 0) + 1;
    });
    const radius = (d) => (o.nodeRadius ? o.nodeRadius(d, linkCount[d.id] || 0)
        : Math.min(5 + (linkCount[d.id] || 0) * 2, 20));

    const simulation = d3.forceSimulation(data.nodes)
        .force('link', d3.forceLink(data.links).id(d => d.id).distance(o.linkDistance))
        .force('charge', d3.forceManyBody().strength(o.charge))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(o.collide))
        .stop();
    if (o.gravity) {
        simulation
            .force('x', d3.forceX(width / 2).strength(o.gravity))
            .force('y', d3.forceY(height / 2).strength(o.gravity));
    }
    // 最初の配置は描く前に落ち着かせる（点が飛び回らず、すぐ枠に収められる）
    simulation.tick(GRAPH_SETTLE_TICKS);

    const link = g.append('g')
        .selectAll('line')
        .data(data.links)
        .join('line')
        .attr('class', 'graph-link');

    const node = g.append('g')
        .selectAll('circle')
        .data(data.nodes)
        .join('circle')
        .attr('class', d => `graph-node ${o.nodeClass(d)}`.trim())
        .attr('r', radius)
        .call(graphDrag(simulation));
    node.append('title').text(d => d.title);

    const below = o.labelPlacement === 'below';
    const shorten = (t) => (o.labelMaxChars && t.length > o.labelMaxChars ? `${t.slice(0, o.labelMaxChars)}…` : t);
    const label = g.append('g')
        .selectAll('text')
        .data(data.nodes)
        .join('text')
        .attr('class', d => `graph-label ${o.nodeClass(d)}`.trim())
        .text(d => shorten(String(d.title)))
        .attr('text-anchor', below ? 'middle' : 'start')
        .attr('dx', d => (below ? 0 : radius(d) + 4))
        .attr('dy', d => (below ? radius(d) + 12 : 4));

    function place() {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);
        node.attr('cx', d => d.x).attr('cy', d => d.y);
        label.attr('x', d => d.x).attr('y', d => d.y);
    }
    place();
    simulation.on('tick', place);

    if (o.hover) {
        node.on('mouseover', function (event, d) {
            const connected = new Set([d.id]);
            data.links.forEach(l => {
                if (idOf(l.source) === d.id) connected.add(idOf(l.target));
                if (idOf(l.target) === d.id) connected.add(idOf(l.source));
            });
            node.classed('is-dimmed', n => !connected.has(n.id));
            label.classed('is-dimmed', n => !connected.has(n.id));
            link.classed('is-dimmed', l => idOf(l.source) !== d.id && idOf(l.target) !== d.id)
                .classed('is-active', l => idOf(l.source) === d.id || idOf(l.target) === d.id);
            d3.select(this).classed('is-hover', true).attr('r', radius(d) + 3);
        }).on('mouseout', function (event, d) {
            node.classed('is-dimmed', false);
            label.classed('is-dimmed', false);
            link.classed('is-dimmed', false).classed('is-active', false);
            d3.select(this).classed('is-hover', false).attr('r', radius(d));
        });
    }

    node.on('click', (event, d) => o.onNodeClick(d));

    // いまの枠の大きさ（描いた後に読みやすい幅の設定などで変わることがあるので、その都度測る）
    function viewSize() {
        const el = svg.node();
        return [el.clientWidth || width, el.clientHeight || height];
    }

    // 全部の点とラベルが枠に収まる倍率に合わせる
    function fitTransform() {
        const [width, height] = viewSize();
        const box = g.node().getBBox();
        if (!box.width && !box.height) return d3.zoomIdentity;
        const pad = o.fitPadding;
        const scale = Math.max(o.minFitScale, Math.min(
            (width - pad * 2) / Math.max(box.width, 1),
            (height - pad * 2) / Math.max(box.height, 1),
            o.maxFitScale));
        const cx = box.x + box.width / 2;
        const cy = box.y + box.height / 2;
        return d3.zoomIdentity.translate(width / 2 - cx * scale, height / 2 - cy * scale).scale(scale);
    }

    function applyTransform(t, duration) {
        if (duration) svg.transition().duration(duration).call(zoom.transform, t);
        else svg.call(zoom.transform, t);
    }

    function zoomToFit(duration = 0) {
        applyTransform(fitTransform(), duration);
    }

    // 指定したノートを枠の中央に寄せる（倍率は枠に収める倍率と minScale の大きいほう）
    function focusNode(id, { minScale = 1.2, duration = 600 } = {}) {
        const target = data.nodes.find(n => n.id === id);
        if (!target) return false;
        const [width, height] = viewSize();
        const scale = Math.max(fitTransform().k, minScale);
        const t = d3.zoomIdentity.translate(width / 2 - target.x * scale, height / 2 - target.y * scale).scale(scale);
        applyTransform(t, duration);
        return true;
    }

    function destroy() {
        simulation.stop();
        container.innerHTML = '';
    }

    return { svg, node, label, zoomToFit, focusNode, destroy };
}

// ドラッグ（動かした点の周りだけシミュレーションを再開する）
function graphDrag(simulation) {
    function dragstarted(event) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        event.subject.fx = event.subject.x;
        event.subject.fy = event.subject.y;
    }
    function dragged(event) {
        event.subject.fx = event.x;
        event.subject.fy = event.y;
    }
    function dragended(event) {
        if (!event.active) simulation.alphaTarget(0);
        event.subject.fx = null;
        event.subject.fy = null;
    }
    return d3.drag()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended);
}
