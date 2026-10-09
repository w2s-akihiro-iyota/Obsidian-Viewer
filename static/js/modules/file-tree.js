// ==============================================
// file-tree.js - サイドバーのファイルツリー（Files タブ）
// ==============================================

const FILE_TREE_OPEN_KEY = 'fileTreeOpenFolders';

function initFileTree() {
    const container = document.getElementById('file-tree');
    const filterInput = document.getElementById('file-tree-filter');
    if (!container) return;

    let tree = [];
    // ユーザーが開いたフォルダ（localStorage に保存する）
    const openFolders = new Set(loadOpenFolders());
    // 開いているノートの祖先フォルダ（表示のときだけ開く。保存はしない）
    let currentAncestors = new Set();
    const currentSlug = getCurrentSlug();

    fetch('/api/tree')
        .then(res => {
            if (!res.ok) throw new Error('Failed to load tree');
            return res.json();
        })
        .then(data => {
            tree = data;
            currentAncestors = new Set(findAncestors(tree, currentSlug) || []);
            render();
            scrollToActive();
        })
        .catch(() => {
            container.innerHTML = '<div class="tree-empty">ファイルツリーを読み込めませんでした</div>';
        });

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
                li.appendChild(buildList(node.children, expandAll));
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
                    const badge = document.createElement('span');
                    badge.className = 'tree-private-badge';
                    badge.textContent = '非公開';
                    link.appendChild(badge);
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
