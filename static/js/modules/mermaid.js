// ==============================================
// mermaid.js - Mermaid diagram rendering
// ==============================================

// Mermaid 本体（vendor の mermaid.min.js。約 3.5MB）は、図のあるページ・プレビューでだけ読み込む。
// 読み込み先は base.html の <meta name="mermaid-src">（テンプレート側の 1 か所に置く）
// 読み込みをあきらめるまでの時間（ms）。過ぎたら図はコードのまま表示し、次に呼ばれたら読み直す
const MERMAID_SCRIPT_TIMEOUT = 15000;
// 読み込み中・読み込み済みの Promise。何度呼ばれても script は 1 本だけにする
let mermaidLoading = null;

function loadMermaid() {
    if (typeof window.mermaid !== 'undefined') return Promise.resolve(window.mermaid);
    if (mermaidLoading) return mermaidLoading;

    const meta = document.querySelector('meta[name="mermaid-src"]');
    const src = meta ? meta.getAttribute('content') : '';
    if (!src) return Promise.reject(new Error('mermaid-src が無い'));

    const script = document.createElement('script');
    mermaidLoading = new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('timeout')), MERMAID_SCRIPT_TIMEOUT);
        script.onload = () => {
            clearTimeout(timer);
            if (typeof window.mermaid === 'undefined') {
                reject(new Error('window.mermaid が無い'));
                return;
            }
            // 読み込んだらすぐ startOnLoad を切る（window の load で勝手に描かせない）。テーマなどの設定もここで付ける
            applyMermaidConfig();
            resolve(window.mermaid);
        };
        script.onerror = () => { clearTimeout(timer); reject(new Error('error')); };
    }).catch(error => {
        mermaidLoading = null;
        script.onload = null;
        script.remove();
        throw error;
    });
    script.src = src;
    document.head.appendChild(script);
    return mermaidLoading;
}

// root の中の ```mermaid のコードブロックを、図を描く div に置き換えて返す。
// 色付け（highlight.js）より先に同期で呼ぶこと。置き換えた後は pre code ではなくなるので色付けの対象から外れる
function convertMermaidBlocks(root) {
    const divs = [];
    root.querySelectorAll('pre code.language-mermaid').forEach((block) => {
        const pre = block.parentElement;
        const mermaidCode = block.textContent;
        const mermaidDiv = document.createElement('div');
        mermaidDiv.className = 'mermaid';
        mermaidDiv.textContent = mermaidCode;
        // テーマを変えて描き直すときに使う元のコード
        mermaidDiv.setAttribute('data-original-code', mermaidCode);
        pre.replaceWith(mermaidDiv);
        divs.push(mermaidDiv);
    });
    return divs;
}

// Mermaid を読めなかったときは、図の div をコードブロックに戻す（色は付けない）
function restoreMermaidBlocks(divs) {
    divs.filter(div => div.isConnected).forEach(div => {
        const pre = document.createElement('pre');
        const code = document.createElement('code');
        code.className = 'language-mermaid';
        code.textContent = div.getAttribute('data-original-code') || div.textContent;
        pre.appendChild(code);
        div.replaceWith(pre);
    });
}

// root の中の Mermaid のブロックを図にする（記事は main.js の initMermaid、エディタのプレビューは editor.js から呼ぶ）。
// ブロックが無ければ Mermaid は読み込まない
function renderMermaidIn(root) {
    const divs = convertMermaidBlocks(root);
    if (divs.length === 0) return;
    loadMermaid()
        .then(mermaid => {
            // 読み込みを待つ間にプレビューが描き直されていたら、もう画面に無い div は描かない
            const nodes = divs.filter(div => div.isConnected);
            if (nodes.length > 0) {
                mermaid.run({ nodes }).catch(err => console.error('Mermaid render error:', err));
            }
        })
        .catch(error => {
            console.warn('Mermaid を読み込めなかったため、図をコードのまま表示します', error);
            restoreMermaidBlocks(divs);
        });
}

function initMermaid() {
    renderMermaidIn(document);
}

function getMermaidTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const mermaidTheme = localStorage.getItem('mermaidTheme') || 'default';
    // 'default'（画面テーマに合わせる）のときは、明るい画面なら default、暗い画面なら dark
    if (mermaidTheme === 'default') {
        return (currentTheme === 'light' || currentTheme === 'letter') ? 'default' : 'dark';
    }
    return mermaidTheme;
}

function applyMermaidConfig() {
    window.mermaid.initialize({
        startOnLoad: false,
        theme: getMermaidTheme(),
        securityLevel: 'loose',
        flowchart: { useMaxWidth: false },
        sequence: { useMaxWidth: false },
        gantt: { useMaxWidth: false },
        journey: { useMaxWidth: false },
        timeline: { useMaxWidth: false },
        class: { useMaxWidth: false },
        state: { useMaxWidth: false },
        erd: { useMaxWidth: false }
    });
}

function updateMermaidConfig() {
    if (typeof window.mermaid === 'undefined') return;

    // テーマを変えたときに、ページ内の図を描き直す（Mermaid をまだ読んでいない＝図が無いページでは何もしない）
    try {
        applyMermaidConfig();

        // Re-render
        const mermaidDivs = document.querySelectorAll('.mermaid');
        mermaidDivs.forEach(div => {
            // Restore original code
            const originalCode = div.getAttribute('data-original-code');
            if (originalCode) {
                div.textContent = originalCode;
                div.removeAttribute('data-processed'); // Clear processed flag
            }
        });

        if (mermaidDivs.length > 0) {
            window.mermaid.run().catch(err => console.error('Mermaid render error:', err));
        }
    } catch (e) {
        console.error('Mermaid update error:', e);
    }
}
