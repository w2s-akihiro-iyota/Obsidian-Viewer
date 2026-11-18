// ==============================================
// article-math.js - 記事ページの数式を KaTeX で描く
// ==============================================
// view.html で、KaTeX と math.js の後ろに defer で読む（defer は書いた順に走る）。描き方は math.js の renderMathIn（エディタと共通）。
// 前は auto-render の <script> の onload に書いていたが、CSP（S-10）でイベント属性は動かないので、外のファイルにした
renderMathIn(document.body);
