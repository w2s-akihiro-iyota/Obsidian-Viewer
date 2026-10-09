// ==============================================
// search.js - Desktop search, mobile search modal, HTMX state, view toggle, accordion
// ==============================================

// 絞り込み条件（tag:会議 / path:"スペース 入り"）。サーバー側の parse_search_query と同じ書式
const SEARCH_FILTER_RE = /(^|\s)(tag|path):("[^"]*"|\S+)/gi;
// クイックスイッチャーの「最近見たノート」に出す件数
const RECENT_NOTES_MAX = 10;
// 検索語のハイライトを入れない要素（図・数式の元テキストを壊さないため）
const HIGHLIGHT_SKIP_SELECTOR = 'script, style, textarea, svg, mark, .mermaid, .katex, .katex-display';

/**
 * 検索結果から開いたノートで、検索語（URL の ?hl=）をハイライトし、最初の一致までスクロールする
 */
function highlightSearchTermsInPage() {
    const params = new URLSearchParams(window.location.search);
    const terms = params.get('hl');
    if (!terms) return;

    // URL コピーや再読み込みにハイライト指定を残さない
    params.delete('hl');
    const rest = params.toString();
    window.history.replaceState(window.history.state, '',
        window.location.pathname + (rest ? `?${rest}` : '') + window.location.hash);

    const run = () => {
        const body = document.querySelector('.markdown-body');
        const regex = buildTermsRegExp(terms);
        if (!body || !regex) return;

        const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, {
            acceptNode: node => (node.parentElement.closest(HIGHLIGHT_SKIP_SELECTOR)
                ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
        });
        const textNodes = [];
        while (walker.nextNode()) textNodes.push(walker.currentNode);

        textNodes.forEach(node => {
            const parts = node.textContent.split(regex);
            if (parts.length === 1) return;
            const fragment = document.createDocumentFragment();
            // split に括弧付きの正規表現を渡すと、奇数番目が一致した部分になる
            parts.forEach((part, i) => {
                if (!part) return;
                if (i % 2 === 1) {
                    const mark = document.createElement('mark');
                    mark.className = 'search-highlight';
                    mark.textContent = part;
                    fragment.appendChild(mark);
                } else {
                    fragment.appendChild(document.createTextNode(part));
                }
            });
            node.replaceWith(fragment);
        });

        const first = body.querySelector('mark.search-highlight');
        if (first && !window.location.hash) first.scrollIntoView({ block: 'center' });
    };

    // 数式（KaTeX）の描画が終わってから。描画前の $...$ に手を入れると数式が崩れる
    if (document.readyState === 'complete') run();
    else window.addEventListener('load', run, { once: true });
}

/**
 * クエリから tag: / path: を除いた検索語
 */
function stripSearchFilters(query) {
    return query.replace(SEARCH_FILTER_RE, ' ').trim().split(/\s+/).filter(Boolean).join(' ');
}

function escapeRegExp(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, ch => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

/**
 * 検索語（空白区切りの各語）に一致する部分を囲む正規表現。語が無ければ null
 */
function buildTermsRegExp(query) {
    const terms = [...new Set(query.split(/\s+/).filter(Boolean))]
        .sort((a, b) => b.length - a.length);
    if (terms.length === 0) return null;
    return new RegExp(`(${terms.map(escapeRegExp).join('|')})`, 'gi');
}

/**
 * クエリ文字列をハイライトしたHTMLを返す（text はエスケープする）
 */
function highlightMatch(text, query) {
    const escapedText = escapeHtml(text);
    const regex = query ? buildTermsRegExp(escapeHtml(query)) : null;
    if (!regex) return escapedText;
    return escapedText.replace(regex, '<mark class="search-highlight">$1</mark>');
}

/**
 * 検索結果アイテムを生成する共通関数
 * query は tag: / path: を除いた検索語。開いた先のノートでもハイライトする
 */
function createSearchResultItem(item, query, closeCallback) {
    const link = document.createElement('a');
    link.href = `/view/${item.slug}` + (query ? `?hl=${encodeURIComponent(query)}` : '');
    link.className = 'search-result-item';
    link.setAttribute('role', 'option');

    // タイトル
    const titleSpan = document.createElement('div');
    titleSpan.className = 'search-result-title';
    titleSpan.innerHTML = highlightMatch(item.title, query);
    link.appendChild(titleSpan);

    // スニペット（本文マッチの場合）
    if (item.snippet) {
        const snippetEl = document.createElement('div');
        snippetEl.className = 'search-result-snippet';
        snippetEl.innerHTML = highlightMatch(item.snippet, query);
        link.appendChild(snippetEl);
    }

    // パス（最近見たノートでは見た時刻）
    const meta = document.createElement('div');
    meta.className = 'search-result-path';
    meta.textContent = item.meta ?? item.path;
    link.appendChild(meta);

    if (closeCallback) {
        link.addEventListener('click', closeCallback);
    }

    return link;
}

function initSearch() {
    // --- Desktop Search ---
    const searchInput = document.getElementById('search-input');
    const searchResults = document.getElementById('search-results');
    let debounceTimer;

    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            clearTimeout(debounceTimer);
            const query = e.target.value;

            if (query.trim() === '') {
                if (searchResults) searchResults.style.display = 'none';
                return;
            }

            debounceTimer = setTimeout(() => {
                fetch(`/api/search?q=${encodeURIComponent(query)}`)
                    .then(response => response.json())
                    .then(data => {
                        if (searchResults) {
                            searchResults.innerHTML = '';
                            if (data.length > 0) {
                                const terms = stripSearchFilters(query);
                                data.forEach(item => {
                                    searchResults.appendChild(createSearchResultItem(item, terms));
                                });
                            } else {
                                const empty = document.createElement('div');
                                empty.className = 'search-result-empty';
                                empty.textContent = 'No results found';
                                searchResults.appendChild(empty);
                            }
                            searchResults.style.display = 'block';
                        }
                    });
            }, DEBOUNCE_DELAY);
        });
    }

    // --- Unified dropdown/search close listener (delegated) ---
    document.addEventListener('click', (e) => {
        // Close all table copy dropdowns
        document.querySelectorAll('.table-copy-dropdown.show').forEach(d => d.classList.remove('show'));

        // Close page menu dropdown
        const pageMenuDropdown = document.getElementById('page-menu-dropdown');
        if (pageMenuDropdown && !e.target.closest('#page-menu-btn')) {
            pageMenuDropdown.classList.remove('show');
        }

        // Close search results
        const searchInput = document.getElementById('search-input');
        const searchResults = document.getElementById('search-results');
        if (searchResults && searchInput && !searchInput.contains(e.target) && !searchResults.contains(e.target)) {
            searchResults.style.display = 'none';
        }
    });

    // --- View toggle functionality (List/Grid) ---
    document.body.addEventListener('click', (e) => {
        const btn = e.target.closest('.view-toggle-btn');
        if (!btn) return;

        if (btn.id === 'list-view-btn') {
            setView('list');
        } else if (btn.id === 'grid-view-btn') {
            setView('grid');
        }
    });

    function setView(view) {
        const fileList = document.querySelector('.file-list');
        const listViewBtn = document.getElementById('list-view-btn');
        const gridViewBtn = document.getElementById('grid-view-btn');

        if (fileList) {
            if (view === 'grid') {
                fileList.classList.add('grid-view');
            } else {
                fileList.classList.remove('grid-view');
            }
        }

        // Update button states if they exist in DOM
        if (listViewBtn && gridViewBtn) {
            if (view === 'grid') {
                listViewBtn.classList.remove('active');
                gridViewBtn.classList.add('active');
            } else {
                listViewBtn.classList.add('active');
                gridViewBtn.classList.remove('active');
            }
        }
        localStorage.setItem('fileListView', view);
    }

    // Set initial view
    const initialView = localStorage.getItem('fileListView') || 'list';
    setView(initialView);

    // --- HTMX State preservation ---
    let accordionState = false;

    document.body.addEventListener('htmx:beforeSwap', (event) => {
        if (event.detail.target.id === 'search-interactive-area') {
            const accordion = document.querySelector('.search-accordion');
            if (accordion) {
                accordionState = accordion.open;
            }
        }
    });

    document.body.addEventListener('htmx:afterSwap', (event) => {
        if (event.detail.target.id === 'search-interactive-area') {
            // Restore View Mode to the NEW file-list
            const currentView = localStorage.getItem('fileListView') || 'list';
            setView(currentView);

            // Restore Accordion State
            const accordion = document.querySelector('.search-accordion');
            if (accordion) {
                accordion.open = accordionState;
            }
        }
    });

    // --- Quick Switcher（Ctrl+K）/ Mobile Search Modal ---
    const mobileSearchBtn = document.getElementById('mobile-search-toggle');
    const searchModal = document.getElementById('search-modal');
    const closeSearchModalBtn = document.getElementById('close-search-modal');
    const modalSearchInput = document.getElementById('modal-search-input');
    const modalSearchResults = document.getElementById('modal-search-results');

    if (searchModal && modalSearchInput && modalSearchResults) {
        let modalDebounceTimer;
        let modalRequestSeq = 0;
        let selectedIndex = -1;

        const getItems = () => Array.from(modalSearchResults.querySelectorAll('.search-result-item'));

        const selectItem = (index) => {
            const items = getItems();
            if (items.length === 0) {
                selectedIndex = -1;
                return;
            }
            selectedIndex = (index + items.length) % items.length;
            items.forEach((item, i) => {
                const selected = i === selectedIndex;
                item.classList.toggle('selected', selected);
                item.setAttribute('aria-selected', String(selected));
            });
            items[selectedIndex].scrollIntoView({ block: 'nearest' });
        };

        const showMessage = (text) => {
            const empty = document.createElement('div');
            empty.className = 'search-result-empty';
            empty.textContent = text;
            modalSearchResults.appendChild(empty);
        };

        // 入力が空のときは最近見たノート（閲覧履歴）を出す
        const renderRecent = () => {
            modalSearchResults.innerHTML = '';
            const currentSlug = getCurrentSlug();
            const recent = getHistory().filter(h => h.path !== currentSlug).slice(0, RECENT_NOTES_MAX);
            if (recent.length === 0) {
                showMessage('最近見たノートはありません');
                selectedIndex = -1;
                return;
            }
            const heading = document.createElement('div');
            heading.className = 'search-modal-section';
            heading.textContent = '最近見たノート';
            modalSearchResults.appendChild(heading);
            recent.forEach(h => {
                modalSearchResults.appendChild(createSearchResultItem(
                    { title: h.title, slug: h.path, meta: formatRelativeTime(h.timestamp) }, '', closeModal));
            });
            selectItem(0);
        };

        const renderResults = (data, query) => {
            modalSearchResults.innerHTML = '';
            if (data.length === 0) {
                showMessage('No results found');
                selectedIndex = -1;
                return;
            }
            const terms = stripSearchFilters(query);
            data.forEach(item => {
                modalSearchResults.appendChild(createSearchResultItem(item, terms, closeModal));
            });
            selectItem(0);
        };

        const openModal = () => {
            searchModal.classList.add('active');
            document.body.classList.add('no-scroll'); // Lock scroll
            renderRecent();
            // visibility の切り替えが終わってからでないとフォーカスできない
            setTimeout(() => modalSearchInput.focus(), 50);
        };

        // Close Modal
        function closeModal() {
            clearTimeout(modalDebounceTimer);
            modalRequestSeq++; // 閉じた後に届いた検索結果は捨てる
            searchModal.classList.remove('active');
            document.body.classList.remove('no-scroll'); // Unlock scroll
            modalSearchInput.value = '';
            modalSearchResults.innerHTML = '';
            selectedIndex = -1;
        }

        if (mobileSearchBtn) mobileSearchBtn.addEventListener('click', openModal);
        if (closeSearchModalBtn) closeSearchModalBtn.addEventListener('click', closeModal);

        // Close on click outside
        searchModal.addEventListener('click', (e) => {
            if (e.target === searchModal) {
                closeModal();
            }
        });

        document.addEventListener('keydown', (e) => {
            // Ctrl+K（Mac は Cmd+K）で開く・閉じる
            if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                if (searchModal.classList.contains('active')) closeModal();
                else openModal();
                return;
            }
            // Close on Escape key
            if (e.key === 'Escape' && searchModal.classList.contains('active')) {
                closeModal();
            }
        });

        modalSearchInput.addEventListener('keydown', (e) => {
            // 日本語入力の変換確定（Enter）や候補選択（↑↓）は横取りしない
            if (e.isComposing || e.keyCode === 229) return;

            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                selectItem(selectedIndex + (e.key === 'ArrowDown' ? 1 : -1));
            } else if (e.key === 'Enter') {
                const item = getItems()[selectedIndex];
                if (!item) return;
                e.preventDefault();
                if (e.ctrlKey || e.metaKey) {
                    window.open(item.href, '_blank', 'noopener');
                    closeModal();
                } else {
                    window.location.href = item.href;
                }
            }
        });

        // マウスで指した候補を選択中にする（Enter で開く対象をそろえる）
        modalSearchResults.addEventListener('mousemove', (e) => {
            const item = e.target.closest('.search-result-item');
            if (!item) return;
            const index = getItems().indexOf(item);
            if (index !== selectedIndex) selectItem(index);
        });

        // Search within Modal
        modalSearchInput.addEventListener('input', (e) => {
            clearTimeout(modalDebounceTimer);
            const query = e.target.value;
            const requestSeq = ++modalRequestSeq;

            if (query.trim() === '') {
                renderRecent();
                return;
            }

            modalDebounceTimer = setTimeout(() => {
                fetch(`/api/search?q=${encodeURIComponent(query)}`)
                    .then(response => response.json())
                    .then(data => {
                        // 後から打った語の結果を、先に打った語の遅い応答で上書きしない
                        if (requestSeq !== modalRequestSeq) return;
                        renderResults(data, query);
                    });
            }, DEBOUNCE_DELAY);
        });
    }

    highlightSearchTermsInPage();

    // --- Accordion Animation Logic ---
    const accordions = document.querySelectorAll('.search-accordion');
    accordions.forEach(el => {
        const summary = el.querySelector('summary');

        // Load saved state
        const savedState = localStorage.getItem('searchAccordionOpen');
        if (savedState !== null) {
            el.open = (savedState === 'true');
        }

        if (!summary) return;

        // Save state on toggle (click)
        summary.addEventListener('click', (e) => {
            e.preventDefault(); // Prevent default toggle

            if (el.classList.contains('animating')) return;

            if (el.open) {
                // Closing
                localStorage.setItem('searchAccordionOpen', 'false');
                el.classList.add('animating');
                const startHeight = el.offsetHeight;
                el.style.height = `${startHeight}px`;

                requestAnimationFrame(() => {
                    const endHeight = summary.offsetHeight;
                    el.style.height = `${endHeight}px`;
                });

                el.addEventListener('transitionend', function onEnd() {
                    el.open = false;
                    el.style.height = ''; // Reset
                    el.classList.remove('animating');
                    el.removeEventListener('transitionend', onEnd);
                }, { once: true });

            } else {
                // Opening
                localStorage.setItem('searchAccordionOpen', 'true');
                el.classList.add('animating');
                const startHeight = el.offsetHeight; // Should be summary height
                el.open = true; // Open to calculate full height
                el.style.height = '';
                const endHeight = el.offsetHeight;

                el.style.height = `${startHeight}px`;

                requestAnimationFrame(() => {
                    el.style.height = `${endHeight}px`;
                });

                el.addEventListener('transitionend', function onEnd() {
                    el.style.height = ''; // Allow auto height
                    el.classList.remove('animating');
                    el.removeEventListener('transitionend', onEnd);
                }, { once: true });
            }
        });
    });
}
