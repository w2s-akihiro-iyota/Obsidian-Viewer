// ==============================================
// file-tree.js - サイドバーのファイルツリー（Files タブ）
// ==============================================

const FILE_TREE_OPEN_KEY = 'fileTreeOpenFolders';
// 前に取ったツリー（/api/tree の応答そのまま）。ページを開くたびにすぐ描けるよう、タブの中だけで持つ（Q-21）。
// sessionStorage はオリジン（ポート）ごとに分かれるので、管理用ポートの非公開ノート入りの木が公開用ポートから読まれることはない。
// 管理者の外部表示の木は、別の箱に入れる（treeCacheKey）
const FILE_TREE_CACHE_KEY = 'fileTreeCache';
// サイドバーのスクロール位置（同じくタブの中だけ）
const FILE_TREE_SCROLL_KEY = 'fileTreeScroll';

function initFileTree() {
    const container = document.getElementById('file-tree');
    const filterInput = document.getElementById('file-tree-filter');
    if (!container) return;

    initFileTreeHints();

    let tree = [];
    // ユーザーが開いたフォルダ（localStorage に保存する）
    const openFolders = new Set(loadOpenFolders());
    // 開いているノートの祖先フォルダ（表示のときだけ開く。保存はしない）
    let currentAncestors = new Set();
    const currentSlug = getCurrentSlug();

    // サイドバーのスクロール位置。ページを移っても同じ位置で描けるよう、タブの中で覚えておく（Q-21）。
    // 覚えるのは画面に出てから（先読み（F-15）されただけのページが、自分で動かした位置で上書きしない）
    const scroller = container.closest('.sidebar-content');
    if (scroller) {
        whenPageShown(() => {
            let saving = false;
            scroller.addEventListener('scroll', () => {
                if (saving) return;
                saving = true;
                requestAnimationFrame(() => {
                    saving = false;
                    saveTreeScroll(scroller.scrollTop);
                });
            }, { passive: true });
        });
    }

    // 前に取った木があれば、まずそれで描く（取り直しを待つと、サイドバーが空のまま出てから埋まる）。
    // そのあと必ず取り直し、中身が変わっていたときだけ描き直す
    const cached = loadCachedTree();
    if (cached) showTree(cached.tree);

    fetch(withViewAs('/api/tree'))
        .then(res => {
            if (!res.ok) throw new Error('Failed to load tree');
            return res.text();
        })
        .then(text => {
            if (cached && text === cached.text) return;
            const data = JSON.parse(text);
            saveCachedTree(text);
            // 前の木を描いたあとの描き直しでは、いまのスクロール位置を動かさない
            showTree(data, Boolean(cached));
        })
        .catch(() => {
            // 前に取った木を描いていれば、そのまま使う
            if (cached) return;
            container.innerHTML = '<div class="tree-empty">ファイルツリーを読み込めませんでした</div>';
        });

    /**
     * 木を描き、サイドバーのスクロール位置を決める。
     * keepScroll でなければ前のページで見ていた位置に戻し、開いているノートがその位置で見えなければ見える所まで動かす
     * （ツリーで次のノートを押しても、サイドバーは動かない）
     */
    function showTree(data, keepScroll = false) {
        const scrollTop = keepScroll ? scroller?.scrollTop : loadTreeScroll();
        // 描き直すとツリーの項目が作り直されるので、キーボードで選んでいた項目を覚えておき、描いたあとに戻す
        const focused = container.contains(document.activeElement) ? document.activeElement.title : null;
        tree = data;
        currentAncestors = new Set(findAncestors(tree, currentSlug) || []);
        render();
        if (focused) {
            const again = Array.from(container.querySelectorAll('.tree-folder, .tree-file')).find(item => item.title === focused);
            again?.focus({ preventScroll: true });
        }
        if (!scroller) return;
        if (scrollTop != null) scroller.scrollTop = scrollTop;
        if (!keepScroll && !isActiveInView()) scrollToActive();
    }

    function isActiveInView() {
        const active = container.querySelector('.tree-file.active');
        // 開いているノートが無い・ほかのタブ（履歴）を出していて見えないときは、動かさない
        if (!active || active.offsetParent === null) return true;
        const item = active.getBoundingClientRect();
        const view = scroller.getBoundingClientRect();
        return item.top >= view.top && item.bottom <= view.bottom;
    }

    if (filterInput) {
        let debounceTimer;
        filterInput.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(render, 150);
        });
        filterInput.addEventListener('keydown', (e) => {
            // 日本語入力の変換確定（Enter）や候補選択（↑↓）は横取りしない
            if (e.isComposing || e.keyCode === 229) return;

            if (e.key === 'Escape' && filterInput.value) {
                filterInput.value = '';
                render();
            } else if (e.key === 'ArrowDown' || e.key === 'Enter') {
                // 打った直後でも、絞り込みを済ませてから動く
                clearTimeout(debounceTimer);
                render();
                const items = getVisibleItems();
                if (items.length === 0) return;
                e.preventDefault();
                if (e.key === 'ArrowDown') {
                    items[0].focus();
                } else {
                    // Enter は一致した最初のノートを開く
                    const firstFile = items.find(item => item.classList.contains('tree-file'));
                    if (firstFile) window.location.href = firstFile.href;
                }
            }
        });
    }

    // Files タブを押したら、開いているノート（無ければ先頭）にフォーカスして、すぐ矢印キーで動けるようにする
    const filesTab = document.querySelector('.sidebar-tab[data-panel="sidebar-files"]');
    if (filesTab) {
        filesTab.addEventListener('click', () => {
            const target = container.querySelector('.tree-file.active') || getVisibleItems()[0];
            if (target) target.focus({ preventScroll: true });
        });
    }

    // --- キーボード操作（ツリーの中にフォーカスがあるとき） ---
    // ↑↓: 前後へ / →: フォルダを開く・中へ / ←: フォルダを閉じる・親へ / Home・End: 先頭・末尾
    // Enter: ノートを開く・フォルダを開閉（a と button の標準動作のまま）
    container.addEventListener('keydown', (e) => {
        const current = e.target.closest('.tree-folder, .tree-file');
        if (!current || e.altKey || e.ctrlKey || e.metaKey) return;

        const items = getVisibleItems();
        const index = items.indexOf(current);
        const folderItem = current.classList.contains('tree-folder') ? current.parentElement : null;
        const isOpen = folderItem && folderItem.classList.contains('open');

        switch (e.key) {
            case 'ArrowDown':
                if (index < items.length - 1) items[index + 1].focus();
                break;
            case 'ArrowUp':
                if (index > 0) items[index - 1].focus();
                else if (filterInput) filterInput.focus();
                break;
            case 'ArrowRight':
                if (folderItem && !isOpen) current.click();
                else if (folderItem) items[index + 1]?.focus();
                break;
            case 'ArrowLeft': {
                if (isOpen) {
                    current.click();
                    break;
                }
                const parentFolder = current.parentElement.parentElement.closest('.tree-folder-item');
                if (parentFolder) parentFolder.querySelector(':scope > .tree-folder').focus();
                break;
            }
            case 'Home':
                items[0]?.focus();
                break;
            case 'End':
                items[items.length - 1]?.focus();
                break;
            default:
                return;
        }
        // 矢印キーでページ本体がスクロールしないように
        e.preventDefault();
    });

    /**
     * いま見えている（閉じたフォルダの中にない）フォルダとノートを上から順に
     */
    function getVisibleItems() {
        return Array.from(container.querySelectorAll('.tree-folder, .tree-file'))
            .filter(item => item.offsetParent !== null);
    }

    function render() {
        const query = filterInput ? filterInput.value.trim().toLowerCase() : '';
        const nodes = query ? filterNodes(tree, query) : tree;

        container.innerHTML = '';
        if (nodes.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'tree-empty';
            empty.textContent = query ? '一致するノートはありません' : 'ノートがありません';
            container.appendChild(empty);
            return;
        }
        // 絞り込み中は、一致したノートが見えるように全フォルダを開く
        container.appendChild(buildList(nodes, Boolean(query)));
    }

    function buildList(nodes, expandAll) {
        const ul = document.createElement('ul');
        ul.className = 'tree-list';

        nodes.forEach(node => {
            const li = document.createElement('li');
            li.className = 'tree-item';

            if (node.type === 'directory') {
                const isOpen = expandAll || openFolders.has(node.path) || currentAncestors.has(node.path);
                li.classList.add('tree-folder-item');
                li.classList.toggle('open', isOpen);

                const folder = document.createElement('button');
                folder.type = 'button';
                folder.className = 'tree-folder';
                folder.title = node.path;
                folder.setAttribute('aria-expanded', String(isOpen));

                const chevron = document.createElement('span');
                chevron.className = 'tree-chevron';
                chevron.setAttribute('aria-hidden', 'true');

                const name = document.createElement('span');
                name.className = 'tree-name';
                name.textContent = node.name;

                const count = document.createElement('span');
                count.className = 'tree-count';
                count.textContent = countNotes(node);

                folder.append(chevron, name, count);
                folder.addEventListener('click', () => {
                    const nowOpen = !li.classList.contains('open');
                    // 閉じていたフォルダの中身は、初めて開いたときに作る（下を参照）
                    if (nowOpen && !li.querySelector(':scope > .tree-list')) {
                        li.appendChild(buildList(node.children, expandAll));
                    }
                    li.classList.toggle('open', nowOpen);
                    folder.setAttribute('aria-expanded', String(nowOpen));
                    if (!expandAll) {
                        // 祖先として自動で開いたフォルダも、閉じたらその状態を守る
                        currentAncestors.delete(node.path);
                        if (nowOpen) openFolders.add(node.path);
                        else openFolders.delete(node.path);
                        saveOpenFolders(openFolders);
                    }
                });

                li.appendChild(folder);
                // 閉じたフォルダの中身は作らない（全部作ると、ページを開くたびに数百項目ぶん固まる。Q-21）
                if (isOpen) li.appendChild(buildList(node.children, expandAll));
            } else {
                const link = document.createElement('a');
                link.className = 'tree-file';
                link.href = `/view/${node.slug}`;
                link.title = node.path;
                if (node.slug === currentSlug) {
                    link.classList.add('active');
                    link.setAttribute('aria-current', 'page');
                }

                const name = document.createElement('span');
                name.className = 'tree-name';
                name.textContent = node.name.replace(/\.md$/i, '');
                link.appendChild(name);

                if (node.published === false) {
                    link.appendChild(createPrivateMark());
                }

                li.appendChild(link);
            }
            ul.appendChild(li);
        });
        return ul;
    }

    function scrollToActive() {
        const active = container.querySelector('.tree-file.active');
        const scroller = container.closest('.sidebar-content');
        if (!active || !scroller) return;
        // scrollIntoView だとページ本体までスクロールするので、サイドバーの中だけ動かす
        const offset = active.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
        scroller.scrollTop += offset - scroller.clientHeight / 3;
    }
}

/**
 * ツリーか絞り込み欄にフォーカスがある間だけ、サイドバーの下の段にキーのヒントを出す（F-9）
 * フォーカスの場所（shortcutPlaceOf）で使えるグループのヒントに切り替える。
 * マウスで押したときは出さない（キーボードで動かしているときだけ。:focus-visible で見分ける。入力欄は常に当てはまる）
 */
function initFileTreeHints() {
    const bar = document.getElementById('file-tree-hints');
    if (!bar) return;
    const sets = Array.from(bar.querySelectorAll('[data-contexts]'));

    const show = (el) => {
        const place = el instanceof Element && el.matches(':focus-visible') ? shortcutPlaceOf(el) : null;
        let shown = false;
        sets.forEach(set => {
            set.hidden = !groupUsableAt(set, place);
            shown = shown || !set.hidden;
        });
        bar.hidden = !shown;
    };

    document.addEventListener('focusin', (e) => show(e.target));
    document.addEventListener('focusout', (e) => {
        // 次のフォーカス先が無い（ページの外・何もない所を押した）ときも消す
        if (!e.relatedTarget) show(null);
    });
}

/**
 * いま開いているノートのスラッグ（記事ページ以外は null）
 */
function getCurrentSlug() {
    const path = window.location.pathname;
    if (!path.startsWith('/view/')) return null;
    try {
        return decodeURIComponent(path.substring('/view/'.length));
    } catch {
        return path.substring('/view/'.length);
    }
}

/**
 * スラッグが一致するノートまでのフォルダのパス一覧（見つからなければ null）
 */
function findAncestors(nodes, slug) {
    if (!slug) return null;
    for (const node of nodes) {
        if (node.type === 'file') {
            if (node.slug === slug) return [];
        } else {
            const found = findAncestors(node.children, slug);
            if (found) return [node.path, ...found];
        }
    }
    return null;
}

/**
 * フォルダ配下のノート数（サブフォルダも含む）
 */
function countNotes(folder) {
    return folder.children.reduce(
        (sum, child) => sum + (child.type === 'file' ? 1 : countNotes(child)), 0);
}

/**
 * ファイル名に query を含むノートと、その祖先フォルダだけを残した木
 */
function filterNodes(nodes, query) {
    const result = [];
    nodes.forEach(node => {
        if (node.type === 'file') {
            if (node.name.toLowerCase().includes(query)) result.push(node);
        } else {
            const children = filterNodes(node.children, query);
            if (children.length > 0) result.push({ ...node, children });
        }
    });
    return result;
}

/**
 * 前に取った木（{ text: 応答の文字列, tree: 読んだ木 }）。無い・壊れているときは null（サーバーから取り直す）
 */
function loadCachedTree() {
    try {
        const text = sessionStorage.getItem(treeCacheKey());
        if (!text) return null;
        const tree = JSON.parse(text);
        return Array.isArray(tree) ? { text, tree } : null;
    } catch {
        return null;
    }
}

function saveCachedTree(text) {
    try {
        sessionStorage.setItem(treeCacheKey(), text);
    } catch {
        // 容量の上限などで書けなくても、次も取り直すだけ
    }
}

/**
 * 木の保存先。管理者の外部表示（?as=public）は公開ノートだけの木なので、通常の表示と分ける
 * （同じ箱だと、外部表示を開いた直後に前の木（非公開入り）が一瞬出る。X-7）
 */
function treeCacheKey() {
    return isPublicView() ? `${FILE_TREE_CACHE_KEY}:public` : FILE_TREE_CACHE_KEY;
}

/**
 * 前のページで見ていたサイドバーのスクロール位置（無ければ null）
 */
function loadTreeScroll() {
    try {
        const saved = sessionStorage.getItem(FILE_TREE_SCROLL_KEY);
        if (saved === null) return null;
        const value = Number(saved);
        return Number.isFinite(value) ? value : null;
    } catch {
        return null;
    }
}

function saveTreeScroll(scrollTop) {
    try {
        sessionStorage.setItem(FILE_TREE_SCROLL_KEY, String(Math.round(scrollTop)));
    } catch {
        // 覚えられなくても、開いているノートの位置まで動かすだけ
    }
}

function loadOpenFolders() {
    try {
        const saved = JSON.parse(localStorage.getItem(FILE_TREE_OPEN_KEY));
        return Array.isArray(saved) ? saved : [];
    } catch {
        return [];
    }
}

function saveOpenFolders(openFolders) {
    localStorage.setItem(FILE_TREE_OPEN_KEY, JSON.stringify([...openFolders]));
}

/**
 * 非公開の印（錠前＋「非公開」）。base.html の <template id="private-mark-template"> を複製する
 * （ノート一覧と同じマクロ partials/_note_macros.html から描いている）
 * 幅が狭いときは CSS で文字を隠し、錠前だけにする（title で「非公開」と分かる）
 */
function createPrivateMark() {
    const template = document.getElementById('private-mark-template');
    // 外部の人の画面には template を置かない（非公開ノートがツリーに来ないので使わない）
    if (!template) return document.createDocumentFragment();
    return template.content.firstElementChild.cloneNode(true);
}
