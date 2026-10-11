// ==============================================
// error-page.js - エラー画面（F-10）のボタン
// 検索ボタン（data-open-search）は search.js が受け持つ
// ==============================================

document.addEventListener('DOMContentLoaded', () => {
    // 500 の「再読み込み」
    document.querySelectorAll('[data-error-reload]').forEach(btn => {
        btn.addEventListener('click', () => location.reload());
    });

    // 管理者の「同期の画面を開く」。同期そのものは設定の「ファイル同期」に任せる（保留した削除の確認などを二重に持たない）
    document.querySelectorAll('[data-open-sync]').forEach(btn => {
        btn.addEventListener('click', openSyncReport);
    });
});
