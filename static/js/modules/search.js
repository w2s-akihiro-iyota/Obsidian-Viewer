// ==============================================
// search.js - Desktop search, mobile search modal, HTMX state, view toggle, accordion
// ==============================================

/**
 * クエリ文字列をハイライトする
 */
function highlightMatch(text, query) {
    if (!query) return text;
    const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return text.replace(new RegExp(`(${escaped})`, 'gi'), '<mark class="search-highlight">$1</mark>');
}

/**
 * 検索結果アイテムを生成する共通関数
 */
function createSearchResultItem(item, query, closeCallback) {
    const link = document.createElement('a');
    link.href = `/view/${item.path}`;
    link.className = 'search-result-item';

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

    // パス
    const meta = document.createElement('div');
    meta.className = 'search-result-path';
    meta.textContent = item.path;
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
                                data.forEach(item => {
                                    searchResults.appendChild(createSearchResultItem(item, query));
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

    // --- Mobile Search Modal Logic ---
    const mobileSearchBtn = document.getElementById('mobile-search-toggle');
    const searchModal = document.getElementById('search-modal');
    const closeSearchModalBtn = document.getElementById('close-search-modal');
    const modalSearchInput = document.getElementById('modal-search-input');
    const modalSearchResults = document.getElementById('modal-search-results');

    if (mobileSearchBtn && searchModal && closeSearchModalBtn) {
        // Open Modal
        mobileSearchBtn.addEventListener('click', () => {
            searchModal.classList.add('active');
            document.body.classList.add('no-scroll'); // Lock scroll
            setTimeout(() => {
                if (modalSearchInput) modalSearchInput.focus();
            }, 100);
        });

        // Close Modal
        const closeModal = () => {
            searchModal.classList.remove('active');
            document.body.classList.remove('no-scroll'); // Unlock scroll
            if (modalSearchInput) modalSearchInput.value = '';
            if (modalSearchResults) modalSearchResults.innerHTML = '';
        };

        closeSearchModalBtn.addEventListener('click', closeModal);

        // Close on click outside
        searchModal.addEventListener('click', (e) => {
            if (e.target === searchModal) {
                closeModal();
            }
        });

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && searchModal.classList.contains('active')) {
                closeModal();
            }
        });

        // Search within Modal
        let modalDebounceTimer;
        if (modalSearchInput) {
            modalSearchInput.addEventListener('input', (e) => {
                clearTimeout(modalDebounceTimer);
                const query = e.target.value;

                if (query.trim() === '') {
                    if (modalSearchResults) modalSearchResults.innerHTML = '';
                    return;
                }

                modalDebounceTimer = setTimeout(() => {
                    fetch(`/api/search?q=${encodeURIComponent(query)}`)
                        .then(response => response.json())
                        .then(data => {
                            if (modalSearchResults) {
                                modalSearchResults.innerHTML = '';
                                if (data.length > 0) {
                                    data.forEach(item => {
                                        modalSearchResults.appendChild(
                                            createSearchResultItem(item, query, closeModal)
                                        );
                                    });
                                } else {
                                    const empty = document.createElement('div');
                                    empty.className = 'search-result-empty';
                                    empty.textContent = 'No results found';
                                    modalSearchResults.appendChild(empty);
                                }
                            }
                        });
                }, DEBOUNCE_DELAY);
            });
        }
    }

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
