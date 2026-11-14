// ==============================================
// public-view-links.js - 外部の人の表示のまま、ほかのノートへ移れるようにする（F-16）
// ==============================================
// 管理者の「外部の人の表示」（body[data-view-as="public"]）では、同じサイトの /view/…・一覧（/）・全体グラフ（/graph）への
// リンクに as=public を付ける（一覧・全体グラフは F-17）。クリック時ではなく href そのものを書き換えるので、新しいタブ・リンクのコピー・先読みでも同じ URL になる。
// あとから差し込まれるリンク（ツリー・検索結果・閲覧履歴・プレビューなど）も MutationObserver で同じ扱いにする。
// 通常の表示に戻るためのリンクは、祖先か自分に data-view-normal を付けて対象から外す。
// as=public の名前と値は app/config.py の VIEW_AS_PARAM / VIEW_AS_PUBLIC と対応（実際の付け外しは core.js の withViewAs。F-17）。

// as=public を付ける移動先か（同じサイトの記事ページ /view/…、一覧 /、全体グラフ /graph。F-17）。
// 先頭が // のもの（別サイト）は、URL にすると origin が変わるので除かれる
function isViewAsTarget(url) {
    if (url.origin !== window.location.origin) return false;
    return url.pathname.startsWith('/view/') || url.pathname === '/' || url.pathname === '/graph';
}

// このリンクに as=public を付けるか（対象の移動先で、通常の表示への導線ではなく、as がまだ無いものだけ）
function shouldAddViewAs(anchor) {
    const href = anchor.getAttribute('href');
    // / で始まるパスだけ（# だけ・相対パス・// で始まる別サイトは対象外）
    if (!href || !href.startsWith('/') || href.startsWith('//')) return false;
    if (anchor.closest('[data-view-normal]')) return false;
    const url = new URL(href, window.location.origin);
    return isViewAsTarget(url) && !url.searchParams.has('as');
}

// root（要素）自身と、その中の a[href] の href を書き換える
function rewriteViewLinks(root) {
    const anchors = root.matches('a[href]') ? [root] : [];
    anchors.push(...root.querySelectorAll('a[href]'));
    anchors.forEach(anchor => {
        if (shouldAddViewAs(anchor)) anchor.setAttribute('href', withViewAs(anchor.getAttribute('href')));
    });
}

function initPublicViewLinks() {
    if (!isPublicView()) return;
    rewriteViewLinks(document.body);
    // childList だけ見る。href の書き換え（attribute）では発火しないので、ループしない
    new MutationObserver(mutations => {
        mutations.forEach(m => m.addedNodes.forEach(node => {
            if (node.nodeType === Node.ELEMENT_NODE) rewriteViewLinks(node);
        }));
    }).observe(document.body, { childList: true, subtree: true });
}
