// ==============================================
// graph.js - D3.js フォースレイアウトグラフ描画
// ==============================================

(function () {
    const canvas = document.getElementById('graph-canvas');
    if (!canvas) return;

    const width = canvas.clientWidth;
    const height = canvas.clientHeight || Math.max(600, window.innerHeight - 120);

    const svg = d3.select('#graph-canvas')
        .append('svg')
        .attr('width', width)
        .attr('height', height);

    // ズーム対応グループ
    const g = svg.append('g');

    const zoom = d3.zoom()
        .scaleExtent([0.1, 4])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
        });
    svg.call(zoom);

    // テーマカラー取得
    function getThemeColors() {
        const style = getComputedStyle(document.documentElement);
        return {
            node: style.getPropertyValue('--accent-purple').trim() || '#7b61ff',
            text: style.getPropertyValue('--text-normal').trim() || '#e0e0e0',
            link: style.getPropertyValue('--border-color').trim() || '#444',
            highlight: '#ff6b6b'
        };
    }

    fetch('/api/graph')
        .then(r => r.json())
        .then(data => {
            if (!data.nodes.length) {
                canvas.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted);">グラフに表示するノードがありません</div>';
                return;
            }

            const colors = getThemeColors();

            // リンク数でノードサイズを決定
            const linkCount = {};
            data.links.forEach(l => {
                linkCount[l.source] = (linkCount[l.source] || 0) + 1;
                linkCount[l.target] = (linkCount[l.target] || 0) + 1;
            });

            const simulation = d3.forceSimulation(data.nodes)
                .force('link', d3.forceLink(data.links).id(d => d.id).distance(100))
                .force('charge', d3.forceManyBody().strength(-200))
                .force('center', d3.forceCenter(width / 2, height / 2))
                .force('collision', d3.forceCollide().radius(30));

            // リンク描画
            const link = g.append('g')
                .selectAll('line')
                .data(data.links)
                .join('line')
                .attr('stroke', colors.link)
                .attr('stroke-opacity', 0.4)
                .attr('stroke-width', 1);

            // ノード描画
            const node = g.append('g')
                .selectAll('circle')
                .data(data.nodes)
                .join('circle')
                .attr('r', d => {
                    const count = linkCount[d.id] || 0;
                    return Math.min(5 + count * 2, 20);
                })
                .attr('fill', colors.node)
                .attr('stroke', 'rgba(255,255,255,0.2)')
                .attr('stroke-width', 1)
                .style('cursor', 'pointer')
                .call(drag(simulation));

            // ラベル描画
            const label = g.append('g')
                .selectAll('text')
                .data(data.nodes)
                .join('text')
                .text(d => d.title)
                .attr('font-size', '10px')
                .attr('fill', colors.text)
                .attr('dx', 12)
                .attr('dy', 4)
                .style('pointer-events', 'none')
                .style('user-select', 'none');

            // ホバーハイライト
            node.on('mouseover', function (event, d) {
                const connected = new Set();
                data.links.forEach(l => {
                    const sid = typeof l.source === 'object' ? l.source.id : l.source;
                    const tid = typeof l.target === 'object' ? l.target.id : l.target;
                    if (sid === d.id) connected.add(tid);
                    if (tid === d.id) connected.add(sid);
                });
                connected.add(d.id);

                node.attr('opacity', n => connected.has(n.id) ? 1 : 0.15);
                link.attr('stroke-opacity', l => {
                    const sid = typeof l.source === 'object' ? l.source.id : l.source;
                    const tid = typeof l.target === 'object' ? l.target.id : l.target;
                    return (sid === d.id || tid === d.id) ? 0.8 : 0.05;
                });
                label.attr('opacity', n => connected.has(n.id) ? 1 : 0.1);

                d3.select(this)
                    .attr('fill', colors.highlight)
                    .attr('r', function () { return +d3.select(this).attr('r') + 3; });
            })
            .on('mouseout', function () {
                node.attr('opacity', 1).attr('fill', colors.node);
                link.attr('stroke-opacity', 0.4);
                label.attr('opacity', 1);

                d3.select(this).attr('r', function (d) {
                    const count = linkCount[d.id] || 0;
                    return Math.min(5 + count * 2, 20);
                });
            });

            // ノードクリックで遷移
            node.on('click', (event, d) => {
                window.location.href = `/view/${d.id}`;
            });

            // シミュレーションtick
            simulation.on('tick', () => {
                link
                    .attr('x1', d => d.source.x)
                    .attr('y1', d => d.source.y)
                    .attr('x2', d => d.target.x)
                    .attr('y2', d => d.target.y);
                node
                    .attr('cx', d => d.x)
                    .attr('cy', d => d.y);
                label
                    .attr('x', d => d.x)
                    .attr('y', d => d.y);
            });
        });

    // ドラッグ
    function drag(simulation) {
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
})();
