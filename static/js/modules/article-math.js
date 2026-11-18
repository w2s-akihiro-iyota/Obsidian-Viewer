// ==============================================
// article-math.js - 記事ページの数式を KaTeX で描く
// ==============================================
// view.html で、KaTeX（katex.min.js・auto-render.min.js）の後ろに defer で読む（defer は書いた順に走る）。
// 前は auto-render の <script> の onload に書いていたが、CSP（S-10）でイベント属性は動かないので、外のファイルにした
(function () {
    if (!window.renderMathInElement || !window.katex) return;

    renderMathInElement(document.body, {
        delimiters: [
            { left: '$$', right: '$$', display: true },
            { left: '$', right: '$', display: false },
            { left: '\\(', right: '\\)', display: false },
            { left: '\\[', right: '\\]', display: true }
        ],
        throwOnError: false
    });
    // Markdown の描画（app/core/markdown.py の dollarmath）が $...$・$$...$$ から作った要素
    document.querySelectorAll('.math.inline').forEach(el => katex.render(el.textContent, el, { throwOnError: false, displayMode: false }));
    document.querySelectorAll('.math.block').forEach(el => katex.render(el.textContent, el, { throwOnError: false, displayMode: true }));
})();
