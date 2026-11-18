// ==============================================
// math.js - 数式を KaTeX で描く（記事ページ・エディタのプレビューで共通。B-30）
// ==============================================
// KaTeX（katex.min.js・auto-render.min.js）の後ろに defer で読む（defer は書いた順に走る）。
// 記事ページは article-math.js が本文に、エディタは editor.js がプレビューを描き直すたびに呼ぶ

// auto-render で数式として拾う区切り
const MATH_DELIMITERS = [
    { left: '$$', right: '$$', display: true },
    { left: '$', right: '$', display: false },
    { left: '\\(', right: '\\)', display: false },
    { left: '\\[', right: '\\]', display: true },
];

/**
 * root の中の数式を描く
 * - 文の中の $...$・\(...\) など（auto-render）
 * - Markdown の描画（app/core/markdown.py の dollarmath）が $...$・$$...$$ から作った .math.inline・.math.block の要素
 *   （中身は区切りの無い TeX なので、auto-render では拾えない。前はエディタのプレビューでこちらを描いていなかった）
 * @param {HTMLElement} root
 * @param {{ignoredClasses?: string[]}} options auto-render で中を見ないクラス（例: Mermaid の図）
 */
function renderMathIn(root, { ignoredClasses = [] } = {}) {
    if (!window.renderMathInElement || !window.katex) return;
    renderMathInElement(root, { delimiters: MATH_DELIMITERS, ignoredClasses, throwOnError: false });
    root.querySelectorAll('.math.inline').forEach(el => katex.render(el.textContent, el, { throwOnError: false, displayMode: false }));
    root.querySelectorAll('.math.block').forEach(el => katex.render(el.textContent, el, { throwOnError: false, displayMode: true }));
}
