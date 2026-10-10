// ==============================================
// local-graph.js - 記事ページの「つながり」の中身（いま読んでいるノートから 1〜2 歩のローカルグラフ）
// 深さの切り替え・読み込み・描画を受け持つ。開閉は local-graph-panel.js（開いたときに onOpen で読み込む）
// データは /api/graph?center=<slug>&depth=1|2、描画は graph-render.js の renderForceGraph
// d3・graph-render.js・API は初めて開いたときに読み込む。d3 を読み込めなかったときは、つながったノートを文字のリンクで並べ、
// 次に開いたときに読み直す
// ==============================================

// 選んだ深さを覚える localStorage のキー（深さの値そのものは view.html のラジオの value）。開閉の状態は覚えない
const LOCAL_GRAPH_DEPTH_KEY = 'localGraphDepth';
// d3 などの読み込みをあきらめるまでの時間（ms）。過ぎたら文字のリンク一覧にする
const LOCAL_GRAPH_SCRIPT_TIMEOUT = 10000;
// この幅より狭い枠では、ラベルを短く切る
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

    const toggle = document.getElementById('local-graph-toggle');
    const canvas = panel.querySelector('.local-graph-canvas');
    const note = panel.querySelector('.local-graph-note');
    const radios = panel.querySelectorAll('input[name="local-graph-depth"]');
    const center = panel.dataset.center;
    const asPublic = panel.dataset.public === 'true';
    const scriptSources = [panel.dataset.d3Src, panel.dataset.renderSrc];

    let lastData = null;
    let lastWidth = 0;
    let requestId = 0;
    let graph = null;       // いま描いているグラフ（描き直す前に destroy する）
    let loadedDepth = null; // いま出している深さ（開き直したときに同じなら読み直さない）
    const scripts = new Map();  // 読み込み中・読み込んだ script（src → Promise）。失敗したものは消して次に読み直す

    // 開閉は local-graph-panel.js。右上のボタンを 1 つにまとめるときは、window.localGraphPanel.setTrigger で開くボタンを差し替える
    window.localGraphPanel = createLocalGraphPanel({
        panel,
        backdrop: document.querySelector('.local-graph-backdrop'),
        closeButton: panel.querySelector('.local-graph-close'),
        trigger: toggle,
        shortcutKey: toggle ? toggle.dataset.shortcutKey : '',
        onOpen: () => {
            const depth = checkedDepth();
            if (depth !== loadedDepth) load(depth);
        },
    });

    // ---------- 深さ ----------

    // localStorage が使えない（プライベートモード等）ときは、覚えずに既定の深さで続ける
    function loadDepth() {
        try { return localStorage.getItem(LOCAL_GRAPH_DEPTH_KEY); } catch (e) { return null; }
    }
    function saveDepth(value) {
        try { localStorage.setItem(LOCAL_GRAPH_DEPTH_KEY, value); } catch (e) { /* 覚えられなくても表示は続ける */ }
    }
    function checkedDepth() {
        return ([...radios].find(r => r.checked) || radios[0]).value;
    }

    const saved = loadDepth();
    const initial = [...radios].find(r => r.value === saved) || radios[0];
    initial.checked = true;
    radios.forEach(r => r.addEventListener('change', () => {
        saveDepth(r.value);
        load(r.value);
    }));

    // ---------- d3 と graph-render.js の読み込み ----------

    // 1 つの script を 1 回だけ読む。失敗・時間切れのときは script を取り除き、次に呼ばれたら読み直す
    function loadScript(src) {
        if (scripts.has(src)) return scripts.get(src);
        const script = document.createElement('script');
        const promise = new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error('timeout')), LOCAL_GRAPH_SCRIPT_TIMEOUT);
            script.onload = () => { clearTimeout(timer); resolve(); };
            script.onerror = () => { clearTimeout(timer); reject(new Error('error')); };
        }).catch(error => {
            scripts.delete(src);
            script.remove();
            throw error;
        });
        scripts.set(src, promise);
        script.src = src;
        document.head.appendChild(script);
        return promise;
    }

    // 読めなかったものがあっても進める（描くときに d3 が無ければ文字のリンク一覧にする）
    const loadLibs = () => Promise.allSettled(scriptSources.map(loadScript));
    const libsReady = () => typeof d3 !== 'undefined' && typeof renderForceGraph !== 'undefined';

    // ---------- 描画 ----------

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
        if (!libsReady()) {
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
        loadedDepth = depth;
        if (!lastData) showMessage('読み込み中…');
        const params = new URLSearchParams({ center, depth: String(depth) });
        if (asPublic) params.set('as', 'public');
        const data = fetch(`/api/graph?${params}`).then(r => (r.ok ? r.json() : Promise.reject(r.status)));
        Promise.all([data, loadLibs()])
            .then(([json]) => {
                if (id !== requestId) return;   // 切り替えが続いたときは最後の結果だけ描く
                setNote(json.truncated ? `つながりが多いため、近い ${json.nodes.length} 件だけを表示しています` : '');
                render(json);
                if (!libsReady()) loadedDepth = null;   // 文字のリンク一覧にしたときは、次に開いたときに読み直す
            })
            .catch(status => {
                if (id !== requestId) return;
                lastData = null;
                loadedDepth = null;     // 次に開いたときに読み直す
                setNote('');
                showMessage(status === 404 ? 'このノートのつながりは表示できません' : 'つながりを読み込めませんでした');
            });
    }

    // 枠の幅が変わったら（パネル ⇔ 768px 以下のシート）描き直す。閉じているあいだ（幅 0）は描かない
    if (window.ResizeObserver) {
        let timer = null;
        new ResizeObserver(() => {
            clearTimeout(timer);
            timer = setTimeout(() => {
                const width = canvas.clientWidth;
                if (lastData && width > 0 && Math.abs(width - lastWidth) > LOCAL_GRAPH_RESIZE_THRESHOLD) render(lastData);
            }, LOCAL_GRAPH_RESIZE_DELAY);
        }).observe(canvas);
    }
})();
