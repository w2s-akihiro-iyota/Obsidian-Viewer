// ==============================================
// local-graph.js - 記事ページの「つながり」（いま読んでいるノートから 1〜2 歩のローカルグラフ）
// データは /api/graph?center=<slug>&depth=1|2、描画は graph-render.js の renderForceGraph
// d3 を読み込めなかったときは、つながったノートを文字のリンクで並べる
// ==============================================

// 選んだ深さを覚える localStorage のキー（深さの値そのものは view.html のラジオの value）
const LOCAL_GRAPH_DEPTH_KEY = 'localGraphDepth';
// この幅より狭い欄（本文の右）では、ラベルを短く切る
const LOCAL_GRAPH_NARROW_WIDTH = 400;
const LOCAL_GRAPH_LABEL_CHARS_NARROW = 10;
const LOCAL_GRAPH_LABEL_CHARS_WIDE = 24;
// 点の半径（中心・1 歩・2 歩）
const LOCAL_GRAPH_RADIUS = { 0: 9, 1: 6, 2: 4.5 };
// 枠に収める倍率の範囲。点が多いときは MIN まで縮め、ラベルが読めない倍率（LABEL_MIN 未満）では中心以外のラベルを隠す
const LOCAL_GRAPH_MIN_FIT_SCALE = 0.3;
const LOCAL_GRAPH_MAX_FIT_SCALE = 1.2;
const LOCAL_GRAPH_LABEL_MIN_SCALE = 0.7;
// 幅の変化がこれ以下なら描き直さない（px）と、描き直すまでの待ち（ms）
const LOCAL_GRAPH_RESIZE_THRESHOLD = 4;
const LOCAL_GRAPH_RESIZE_DELAY = 150;

(function () {
    const panel = document.getElementById('local-graph');
    if (!panel) return;

    const canvas = panel.querySelector('.local-graph-canvas');
    const note = panel.querySelector('.local-graph-note');
    const radios = panel.querySelectorAll('input[name="local-graph-depth"]');
    const center = panel.dataset.center;
    const asPublic = panel.dataset.public === 'true';

    let lastData = null;
    let lastWidth = 0;
    let requestId = 0;
    let graph = null;   // いま描いているグラフ（描き直す前に destroy する）

    // localStorage が使えない（プライベートモード等）ときは、覚えずに既定の深さで続ける
    function loadDepth() {
        try { return localStorage.getItem(LOCAL_GRAPH_DEPTH_KEY); } catch (e) { return null; }
    }
    function saveDepth(value) {
        try { localStorage.setItem(LOCAL_GRAPH_DEPTH_KEY, value); } catch (e) { /* 覚えられなくても表示は続ける */ }
    }

    function showMessage(text) {
        clearGraph();
        const p = document.createElement('p');
        p.className = 'local-graph-empty';
        p.textContent = text;
        canvas.replaceChildren(p);
    }

    function setNote(text) {
        note.textContent = text || '';
        note.hidden = !text;
    }

    // d3 が無いときの代わり: 距離ごとにリンクを並べる
    function renderList(data) {
        const list = document.createElement('ul');
        list.className = 'local-graph-list';
        data.nodes
            .filter(n => n.distance > 0)
            .sort((a, b) => a.distance - b.distance || String(a.title).localeCompare(String(b.title), 'ja'))
            .forEach(n => {
                const li = document.createElement('li');
                const a = document.createElement('a');
                a.href = `/view/${n.slug}`;
                a.textContent = n.title;
                li.appendChild(a);
                if (n.distance > 1) {
                    const hop = document.createElement('span');
                    hop.className = 'local-graph-hop';
                    hop.textContent = `${n.distance} 歩`;
                    li.appendChild(hop);
                }
                list.appendChild(li);
            });
        canvas.replaceChildren(list);
    }

    function clearGraph() {
        if (graph) {
            graph.destroy();
            graph = null;
        }
    }

    function render(data) {
        clearGraph();
        lastData = data;
        lastWidth = canvas.clientWidth;
        if (data.nodes.length <= 1) {
            showMessage('リンクでつながったノートはありません');
            return;
        }
        if (typeof d3 === 'undefined') {
            renderList(data);
            return;
        }
        graph = renderForceGraph(canvas, data, {
            linkDistance: 60,
            charge: -150,
            labelPlacement: 'below',
            labelMaxChars: canvas.clientWidth < LOCAL_GRAPH_NARROW_WIDTH
                ? LOCAL_GRAPH_LABEL_CHARS_NARROW : LOCAL_GRAPH_LABEL_CHARS_WIDE,
            minFitScale: LOCAL_GRAPH_MIN_FIT_SCALE,
            maxFitScale: LOCAL_GRAPH_MAX_FIT_SCALE,
            hideLabelsBelow: LOCAL_GRAPH_LABEL_MIN_SCALE,
            zoomable: false,           // 記事のスクロールを奪わない
            hover: false,
            fitPadding: 12,
            nodeRadius: d => LOCAL_GRAPH_RADIUS[d.distance] ?? LOCAL_GRAPH_RADIUS[2],
            nodeClass: d => (d.distance === 0 ? 'is-center' : `is-hop${d.distance}`),
            ariaLabel: `${panel.dataset.title} のつながり`,
        });
        graph.zoomToFit();
    }

    function load(depth) {
        const id = ++requestId;
        const params = new URLSearchParams({ center, depth: String(depth) });
        if (asPublic) params.set('as', 'public');
        fetch(`/api/graph?${params}`)
            .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
            .then(data => {
                if (id !== requestId) return;   // 切り替えが続いたときは最後の結果だけ描く
                setNote(data.truncated ? `つながりが多いため、近い ${data.nodes.length} 件だけを表示しています` : '');
                render(data);
            })
            .catch(status => {
                if (id !== requestId) return;
                lastData = null;
                setNote('');
                showMessage(status === 404 ? 'このノートのつながりは表示できません' : 'つながりを読み込めませんでした');
            });
    }

    const saved = loadDepth();
    const initial = [...radios].find(r => r.value === saved) || radios[0];
    initial.checked = true;
    radios.forEach(r => r.addEventListener('change', () => {
        saveDepth(r.value);
        load(r.value);
    }));
    load(initial.value);

    // 幅が変わったら（右の欄 ⇔ 記事の下）描き直す
    if (window.ResizeObserver) {
        let timer = null;
        new ResizeObserver(() => {
            clearTimeout(timer);
            timer = setTimeout(() => {
                if (lastData && Math.abs(canvas.clientWidth - lastWidth) > LOCAL_GRAPH_RESIZE_THRESHOLD) render(lastData);
            }, LOCAL_GRAPH_RESIZE_DELAY);
        }).observe(canvas);
    }
})();
