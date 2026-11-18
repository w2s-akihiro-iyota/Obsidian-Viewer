// ==============================================
// graph-render.js - D3.js のフォースレイアウトでグラフを描く
// 全体グラフ（graph.js）と記事ページのローカルグラフ（local-graph.js）で共通
// 色は CSS（graph.css の .graph-node 等）が CSS 変数で塗るので、テーマを切り替えても追従する
// ==============================================

// フォースレイアウトが落ち着くまでの tick 数（d3 の既定 alphaMin・alphaDecay で約 300）
const GRAPH_SETTLE_TICKS = 300;
// 落ち着くまでの計算を、1 回にこの時間（ms）までに分ける。あいだに画面を描かせて、固めない（Q-37。
// 771 ノードの全体グラフでは 300 tick に 1 秒以上かかり、まとめて計算すると画面が止まっていた）。
// 続きは MessageChannel で呼ぶ（setTimeout は続けて呼ぶと 4ms 以上待たされ、全体で 1.5 秒ほど遅くなった）
const GRAPH_SETTLE_SLICE_MS = 12;
// 最初の 1 回だけは、長いタスク（50ms）にならない長さまで計算する。点が少ないグラフ（つながりなど）はここで終わり、
// メッセージを出さずにすぐ描く（12ms だと、d3 の処理がまだ温まっていない初回は点 3 つでも終わらないことがあった）
const GRAPH_SETTLE_FIRST_SLICE_MS = 45;
const GRAPH_SETTLING_MESSAGE = '配置を計算しています…';
// 覚えた配置（Q-39）の形の版。形を変えたら上げる（古い形は読まずに計算し直す）
const GRAPH_LAYOUT_STORE_VERSION = 1;
// 拡大縮小できる倍率の範囲（枠に収めるときの最小倍率の既定値もこれ）
const GRAPH_MIN_ZOOM = 0.05;
const GRAPH_MAX_ZOOM = 4;

/**
 * container の中に SVG のグラフを描く
 * @param {HTMLElement} container 描画先（中身は置き換える）
 * @param {{nodes: Array, links: Array}} data /api/graph の JSON
 * @param {object} options 下の defaults を参照
 * @returns {{svg, node, label, ready: Promise, zoomToFit: Function, focusNode: Function, destroy: Function}}
 *   点は配置が落ち着いてから container に入れる（点が飛び回らない）。計算が 1 回の切れ目で終わらないときは、
 *   そのあいだ GRAPH_SETTLING_MESSAGE を出す。入れ終わると ready が解決する。zoomToFit・focusNode は ready のあとに呼ぶ
 *   destroy は描き直す前に呼ぶ（計算とシミュレーションを止め、container を空にする。そのあと ready は解決しない）
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
        onNodeClick: (d) => { window.location.href = withViewAs(viewUrl(d.slug)); },
        layoutKey: null,            // 配置を localStorage に覚えるキー（Q-39。全体グラフだけ）。点と線がまったく同じなら、次は計算せずに描く
    }, options);

    container.innerHTML = '';
    const width = container.clientWidth;
    const height = container.clientHeight || Math.max(600, window.innerHeight - 120);

    // 配置が落ち着くまでは container に入れない（下の settle）
    const svg = d3.create('svg')
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

    // 最初の配置は、描く前に落ち着かせる（点が飛び回らず、すぐ枠に収められる）。
    // 計算は GRAPH_SETTLE_SLICE_MS ずつに分け、終わらなければ次のタスクで続ける（あいだに画面が描ける）
    let destroyed = false;
    let channel = null;
    let ticks = 0;

    // 覚えた配置が今の点と線のものなら、計算せずにそれを使う（Q-39）。位置は枠の真ん中からのずれで覚える
    const centerX = width / 2;
    const centerY = height / 2;
    const signature = o.layoutKey ? graphLayoutSignature(data.nodes, data.links, idOf) : null;
    const saved = signature ? readGraphLayout(o.layoutKey, signature) : null;
    const restored = Boolean(saved) && data.nodes.every(n => Array.isArray(saved[n.id]));
    if (restored) {
        data.nodes.forEach(n => {
            n.x = centerX + saved[n.id][0];
            n.y = centerY + saved[n.id][1];
            n.vx = 0;
            n.vy = 0;
        });
        simulation.alpha(simulation.alphaMin());   // 落ち着いたあとと同じ（ドラッグしたときだけ動き出す）
        ticks = GRAPH_SETTLE_TICKS;
    }
    function settleSlice(budgetMs) {
        const until = performance.now() + budgetMs;
        while (ticks < GRAPH_SETTLE_TICKS && performance.now() < until) {
            simulation.tick();
            ticks++;
        }
        return ticks >= GRAPH_SETTLE_TICKS;
    }
    const ready = new Promise((resolve) => {
        function show() {
            if (signature && !restored) saveGraphLayout(o.layoutKey, signature, data.nodes, centerX, centerY);
            place();
            simulation.on('tick', place);
            container.replaceChildren(svg.node());
            resolve();
        }
        if (settleSlice(GRAPH_SETTLE_FIRST_SLICE_MS)) {
            show();
            return;
        }
        const message = document.createElement('div');
        message.className = 'graph-message';
        message.setAttribute('role', 'status');
        message.textContent = GRAPH_SETTLING_MESSAGE;
        container.replaceChildren(message);
        channel = new MessageChannel();
        channel.port1.onmessage = () => {
            if (destroyed) return;
            if (settleSlice(GRAPH_SETTLE_SLICE_MS)) {
                channel.port1.close();
                show();
            } else {
                channel.port2.postMessage(null);
            }
        };
        channel.port2.postMessage(null);
    });

    function destroy() {
        destroyed = true;
        if (channel) channel.port1.close();
        simulation.stop();
        container.innerHTML = '';
    }

    return { svg, node, label, ready, zoomToFit, focusNode, destroy };
}

// 点と線の組み合わせを表す短い文字列（並び順に左右されない）。覚えた配置が今のグラフのものかを見分ける（Q-39）
function graphLayoutSignature(nodes, links, idOf) {
    const ids = nodes.map(n => String(n.id)).sort();
    const pairs = links.map(l => `${idOf(l.source)}\u0000${idOf(l.target)}`).sort();
    let hash = 0x811c9dc5;   // FNV-1a（32 ビット）
    for (const text of [ids.join('\u0001'), pairs.join('\u0001')]) {
        for (let i = 0; i < text.length; i++) {
            hash = Math.imul(hash ^ text.charCodeAt(i), 0x01000193);
        }
    }
    return `${ids.length}:${pairs.length}:${(hash >>> 0).toString(36)}`;
}

// 覚えた配置（点の id → 枠の真ん中からのずれ [x, y]）。無い・形が違う・別の点と線のものなら null
function readGraphLayout(key, signature) {
    try {
        const saved = JSON.parse(localStorage.getItem(key));
        if (saved && saved.version === GRAPH_LAYOUT_STORE_VERSION && saved.signature === signature) return saved.positions;
    } catch (e) {
        // 読めなければ計算し直す
    }
    return null;
}

function saveGraphLayout(key, signature, nodes, centerX, centerY) {
    const round = v => Math.round(v * 10) / 10;
    const positions = Object.fromEntries(nodes.map(n => [n.id, [round(n.x - centerX), round(n.y - centerY)]]));
    try {
        localStorage.setItem(key, JSON.stringify({ version: GRAPH_LAYOUT_STORE_VERSION, signature, positions }));
    } catch (e) {
        // 覚えられなくても描ける（容量を超えた・保存できないブラウザ）
    }
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
