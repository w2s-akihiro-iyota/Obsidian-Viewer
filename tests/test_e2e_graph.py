"""グラフの描画（graph-render.js の renderForceGraph）の E2E（Q-37。仕組みは conftest.py の e2e）

- 点の配置は、描く前に落ち着くまで計算する（点が飛び回らない。F-8）。点が多いときは、その計算を少しずつに分けて
  あいだに画面を描かせる（画面を固めない）。計算しているあいだは「配置を計算しています…」を出し、点はまだ出さない
- 点が少ない（ローカルグラフなど）ときは、最初の 1 回で計算が終わるので、今までどおりすぐ描く（メッセージは出さない）
- 計算が終わったことは ready（Promise）で分かる。枠に収める（zoomToFit）のは ready のあと
- 計算の途中で destroy したら、あとから描かない

全体グラフのページ（/graph）を開き、そこで読み込まれた renderForceGraph に、作った点と線を渡して確かめる
"""
from conftest import import_playwright

expect = import_playwright().expect

# 点が多いグラフの点の数。今の実データ（771）の約 2 倍にして、速い PC でも 1 回の切れ目では計算が終わらないようにする
MANY_NODES = 1500
FEW_NODES = 3
SETTLING_MESSAGE = "配置を計算しています"
GRAPH_BOX = "#e2e-graph-box"

# 点と線を作って、新しい枠に renderForceGraph で描く。描いた直後の枠の様子を window.__e2e に残す
# （線は 1 つの点から 3 本ずつ。番号を掛け算でずらして、まとまりの無いつながりにする）
_RENDER = """n => {
    const nodes = Array.from({ length: n }, (_, i) => ({ id: `n${i}`, slug: `n${i}`, title: `ノート${i}` }));
    const links = [];
    for (let i = 0; i < n; i++) {
        for (const k of [7, 13, 31]) {
            const j = (i * k + 1) % n;
            if (j !== i) links.push({ source: `n${i}`, target: `n${j}` });
        }
    }
    const box = document.createElement('div');
    box.id = 'e2e-graph-box';
    box.style.cssText = 'width: 800px; height: 600px';
    document.body.appendChild(box);
    const state = { frames: 0, settled: false, nodes };
    const countFrames = () => { if (state.settled) return; state.frames++; requestAnimationFrame(countFrames); };
    requestAnimationFrame(countFrames);
    const graph = renderForceGraph(box, { nodes, links }, {});
    state.graph = graph;
    state.rightAfter = {
        svg: box.querySelector('svg') !== null,
        text: box.textContent.trim(),
        status: box.querySelector('[role="status"]') !== null,
    };
    Promise.resolve(graph.ready).then(() => { state.settled = true; });
    window.__e2e = state;
    return state.rightAfter;
}"""

_SETTLED = "() => window.__e2e.settled"


def _render(page, n):
    return page.evaluate(_RENDER, n)


def test_点が多いと計算を分けて画面を固めず_落ち着くまで点を出さない(e2e):
    page = e2e.open_path("/graph")
    right_after = _render(page, MANY_NODES)
    assert not right_after["svg"], "計算が終わる前に点を描いた（描いた直後に枠の中に svg がある）"
    assert SETTLING_MESSAGE in right_after["text"] and right_after["status"], f"計算中のメッセージが出ていない: {right_after}"

    # 計算は数秒かかる（expect の上限より長い）ので、ここだけ上限を延ばして待つ
    page.wait_for_function(_SETTLED, timeout=60_000, polling=200)
    after = page.evaluate("""() => {
        const box = document.querySelector('#e2e-graph-box');
        return {
            frames: window.__e2e.frames,
            circles: box.querySelectorAll('svg circle').length,
            message: box.textContent.includes('配置を計算しています'),
            placed: window.__e2e.nodes.every(d => Number.isFinite(d.x) && Number.isFinite(d.y)),
        };
    }""")
    # 計算のあいだに画面を何度も描けた（固めていない）
    assert after["frames"] >= 5, f"計算のあいだに画面を描けていない（{after['frames']} フレーム）"
    assert after["circles"] == MANY_NODES and not after["message"] and after["placed"], f"落ち着いたあとの描き方がおかしい: {after}"


def test_点が少ないとすぐ描きメッセージを出さない(e2e):
    page = e2e.open_path("/graph")
    right_after = _render(page, FEW_NODES)
    assert right_after["svg"] and SETTLING_MESSAGE not in right_after["text"], f"少ない点なのにすぐ描いていない: {right_after}"
    e2e.wait_until(page, _SETTLED, "少ない点のグラフで ready が解決しない")
    expect(page.locator(f"{GRAPH_BOX} svg circle")).to_have_count(FEW_NODES)


def test_計算の途中でdestroyしたら_あとから描かない(e2e):
    page = e2e.open_path("/graph")
    _render(page, MANY_NODES)
    page.evaluate("() => window.__e2e.graph.destroy()")
    # 途中で止めなければ計算が終わっているくらい待つ（MANY_NODES は数秒）
    page.wait_for_timeout(8_000)
    box = page.locator(GRAPH_BOX)
    expect(box.locator("svg")).to_have_count(0)
    expect(box).to_have_text("")


def test_全体グラフは計算が終わってから枠に収める(e2e):
    page = e2e.open_path("/graph")
    expect(page.locator("#graph-canvas svg circle").first).to_be_visible()
    # zoomToFit が g に transform を付ける（計算の前に呼ぶと、点が無いので付かない・ずれる）
    e2e.wait_until(page, """() => {
        const g = document.querySelector('#graph-canvas svg > g');
        return Boolean(g) && /scale\\(/.test(g.getAttribute('transform') || '');
    }""", "全体グラフを枠に収めていない（g に transform が無い）")
