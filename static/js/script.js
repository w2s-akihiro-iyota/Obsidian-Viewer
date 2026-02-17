let MESSAGES = { errors: {}, warnings: {}, system: {} };

async function loadMessages() {
    try {
        const response = await fetch('/api/messages');
        if (response.ok) {
            MESSAGES = await response.json();
            console.log("Messages loaded successfully");
        }
    } catch (err) {
        console.error("Failed to load messages", err);
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    // Load messages first
    await loadMessages();
    // Theme toggle functionality
    // Theme toggle functionality (Now handled via Settings)
    // const themeToggleBtn = document.getElementById('theme-toggle'); 
    // Kept comment for reference or valid if we re-add a quick toggle later.

    // Load saved theme or default to dark
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);

    // Update highlight.js theme
    const highlightThemeLink = document.getElementById('highlight-theme');
    const updateHighlightTheme = (theme) => {
        if (highlightThemeLink) {
            if (theme === 'light') {
                highlightThemeLink.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css';
            } else {
                highlightThemeLink.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css';
            }
        }
    };
    updateHighlightTheme(savedTheme);

    // Old toggle logic removed

    // Mermaid diagram rendering

    // Mermaid diagram rendering
    function initMermaid() {
        if (typeof window.mermaid === 'undefined') {
            // Mermaid not loaded yet, retry after a short delay
            setTimeout(initMermaid, 100);
            return;
        }

        // Find all mermaid code blocks (first run)
        const mermaidBlocks = document.querySelectorAll('pre code.language-mermaid');
        mermaidBlocks.forEach((block) => {
            const pre = block.parentElement;
            const mermaidCode = block.textContent;

            // Create a div for mermaid rendering
            const mermaidDiv = document.createElement('div');
            mermaidDiv.className = 'mermaid';
            mermaidDiv.textContent = mermaidCode;
            // Store original code for re-rendering
            mermaidDiv.setAttribute('data-original-code', mermaidCode);

            // Replace the pre element with the mermaid div
            pre.replaceWith(mermaidDiv);
        });

        updateMermaidConfig();
    }

    function updateMermaidConfig() {
        if (typeof window.mermaid === 'undefined') return;

        const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
        let mermaidTheme = localStorage.getItem('mermaidTheme') || 'default';

        // If 'default' (Adaptive), choose based on current mode
        if (mermaidTheme === 'default') {
            if (currentTheme === 'light' || currentTheme === 'letter') {
                mermaidTheme = 'default';
            } else {
                mermaidTheme = 'dark';
            }
        }

        try {
            // Re-initialize mermaid
            window.mermaid.initialize({
                startOnLoad: false,
                theme: mermaidTheme,
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

    // Expose for usage in settings
    window.updateMermaidConfig = updateMermaidConfig;

    // Initialize mermaid after page load
    initMermaid();

    // Render task lists after page load
    // renderTaskLists(); // Removed: handled by backend markdown plugin

    // Table copy functionality
    function addTableCopyButtons() {
        const tables = document.querySelectorAll('.markdown-body table');

        tables.forEach((table) => {
            // Create wrapper for table
            const wrapper = document.createElement('div');
            wrapper.className = 'table-wrapper';
            table.parentNode.insertBefore(wrapper, table);
            wrapper.appendChild(table);

            // Create copy button container
            const copyContainer = document.createElement('div');
            copyContainer.className = 'table-copy-container';

            // Create copy button
            const copyBtn = document.createElement('button');
            copyBtn.type = 'button';
            copyBtn.className = 'table-copy-btn';
            copyBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                </svg>
                <span>Copy</span>
            `;

            // Create dropdown menu
            const dropdown = document.createElement('div');
            dropdown.className = 'table-copy-dropdown';
            dropdown.innerHTML = `
                <button type="button" class="copy-option" data-format="excel">Excel Format</button>
                <button type="button" class="copy-option" data-format="markdown">Markdown Format</button>
            `;

            copyContainer.appendChild(copyBtn);
            copyContainer.appendChild(dropdown);
            wrapper.insertBefore(copyContainer, table);

            // Toggle dropdown
            copyBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                e.preventDefault();
                dropdown.classList.toggle('show');
            });

            // Close dropdown when clicking outside
            document.addEventListener('click', () => {
                dropdown.classList.remove('show');
            });

            // Copy options
            dropdown.querySelectorAll('.copy-option').forEach((option) => {
                option.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    const format = option.dataset.format;
                    await copyTableToClipboard(table, format);
                    dropdown.classList.remove('show');

                    // Show feedback
                    const originalText = copyBtn.innerHTML;
                    copyBtn.innerHTML = `
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                        <span>Copied!</span>
                    `;
                    setTimeout(() => {
                        copyBtn.innerHTML = originalText;
                    }, 2000);
                });
            });
        });
    }

    async function copyTableToClipboard(table, format) {
        let content = '';

        if (format === 'excel') {
            // TSV format for Excel
            const rows = table.querySelectorAll('tr');
            rows.forEach((row) => {
                const cells = row.querySelectorAll('th, td');
                const rowData = Array.from(cells).map(cell => {
                    let text = cell.textContent.trim();
                    // Escape quotes and wrap in quotes if necessary for Excel
                    if (text.includes('"') || text.includes('\t') || text.includes('\n')) {
                        text = '"' + text.replace(/"/g, '""') + '"';
                    }
                    return text;
                }).join('\t');
                content += rowData + '\n';
            });
        } else if (format === 'markdown') {
            // Markdown format
            const headerRow = table.querySelector('thead tr');
            const bodyRows = table.querySelectorAll('tbody tr');

            // Header
            if (headerRow) {
                const headers = Array.from(headerRow.querySelectorAll('th')).map(th => th.textContent.trim());
                content += '| ' + headers.join(' | ') + ' |\n';
                content += '| ' + headers.map(() => '---').join(' | ') + ' |\n';
            }

            // Body
            bodyRows.forEach((row) => {
                const cells = Array.from(row.querySelectorAll('td')).map(td => td.textContent.trim());
                content += '| ' + cells.join(' | ') + ' |\n';
            });
        }

        // Copy to clipboard with fallback
        try {
            await navigator.clipboard.writeText(content);
            console.log('Table copied to clipboard in', format, 'format via API');
        } catch (err) {
            console.warn('Clipboard API failed, trying fallback:', err);
            const textarea = document.createElement('textarea');
            textarea.value = content;
            textarea.style.position = 'fixed'; // Avoid scrolling
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            try {
                document.execCommand('copy');
                console.log('Table copied to clipboard via execCommand');
            } catch (fallbackErr) {
                console.error('Fallback copy failed:', fallbackErr);
                alert('Copy failed. Please try manually.');
            } finally {
                document.body.removeChild(textarea);
            }
        }
    }

    // Add copy buttons to all tables
    addTableCopyButtons();

    // Page menu (three-dot menu) functionality
    const pageMenuBtn = document.getElementById('page-menu-btn');
    const pageMenuDropdown = document.getElementById('page-menu-dropdown');
    const exportPdfBtn = document.getElementById('export-pdf-btn');

    if (pageMenuBtn && pageMenuDropdown) {
        // Toggle dropdown
        pageMenuBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            pageMenuDropdown.classList.toggle('show');
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', () => {
            pageMenuDropdown.classList.remove('show');
        });
    }

    // PDF export functionality
    if (exportPdfBtn) {
        exportPdfBtn.addEventListener('click', () => {
            window.print();
        });
    }

    // Copy URL functionality
    const copyUrlBtn = document.getElementById('copy-url-btn');
    if (copyUrlBtn) {
        copyUrlBtn.addEventListener('click', async () => {
            const title = document.title.replace(' - Obsidian Viewer', '');
            let url = window.location.href;

            try {
                // Fetch current config to check for base_url
                const configRes = await fetch('/api/config');
                if (configRes.ok) {
                    const config = await configRes.json();
                    if (config.base_url) {
                        const baseUrl = config.base_url.replace(/\/$/, ''); // Remove trailing slash
                        const origin = window.location.origin;
                        url = url.replace(origin, baseUrl);
                    }
                }
            } catch (err) {
                console.warn("Failed to fetch config for base_url, using current URL:", err);
            }

            try {
                // Generate HTML and Text versions
                const blobHtml = new Blob([`<a href="${url}">${title}</a>`], { type: 'text/html' });
                const blobText = new Blob([url], { type: 'text/plain' });

                // Use Clipboard API for both formats if available
                if (navigator.clipboard && navigator.clipboard.write) {
                    try {
                        const data = [new ClipboardItem({
                            'text/html': blobHtml,
                            'text/plain': blobText
                        })];
                        await navigator.clipboard.write(data);
                    } catch (itemErr) {
                        console.warn("ClipboardItem failed, falling back to writeText:", itemErr);
                        await navigator.clipboard.writeText(url);
                    }
                } else {
                    // Fallback to text only if write() is not supported
                    await navigator.clipboard.writeText(url);
                }

                showToast(MESSAGES.system?.S002 || "URLをコピーしました", "success");
            } catch (err) {
                console.error("Failed to copy URL:", err);

                // Final fallback using textarea
                const textarea = document.createElement('textarea');
                textarea.value = url;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.focus();
                textarea.select();
                try {
                    document.execCommand('copy');
                    showToast(MESSAGES.system?.S002 || "URLをコピーしました", "success");
                } catch (fallbackErr) {
                    console.error('Final fallback copy failed:', fallbackErr);
                    showToast(MESSAGES.system?.S003 || "コピーに失敗しました", "error");
                } finally {
                    document.body.removeChild(textarea);
                }
            }
        });
    }

    // Scroll to Top Button
    const scrollToTopBtn = document.getElementById('scroll-to-top');

    if (scrollToTopBtn) {
        // Show/hide button based on scroll position
        window.addEventListener('scroll', () => {
            if (window.pageYOffset > 300) {
                scrollToTopBtn.classList.add('show');
            } else {
                scrollToTopBtn.classList.remove('show');
            }
        });

        // Scroll to top on click
        scrollToTopBtn.addEventListener('click', () => {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }

    // Add copy button to code blocks
    document.querySelectorAll('pre code').forEach((codeBlock) => {
        const pre = codeBlock.parentNode;
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'copy-button';
        button.textContent = 'Copy';
        button.style.position = 'absolute';
        button.style.top = '5px';
        button.style.right = '5px';
        button.style.padding = '5px 10px';
        button.style.background = 'rgba(255, 255, 255, 0.1)';
        button.style.border = 'none';
        button.style.borderRadius = '4px';
        button.style.color = '#dcddde';
        button.style.cursor = 'pointer';
        button.style.fontSize = '12px';
        button.style.opacity = '0';
        button.style.transition = 'opacity 0.2s';

        pre.style.position = 'relative';
        pre.appendChild(button);

        pre.addEventListener('mouseenter', () => {
            button.style.opacity = '1';
        });

        pre.addEventListener('mouseleave', () => {
            button.style.opacity = '0';
        });

        button.addEventListener('click', () => {
            navigator.clipboard.writeText(codeBlock.textContent).then(() => {
                button.textContent = 'Copied!';
                setTimeout(() => {
                    button.textContent = 'Copy';
                }, 2000);
            });
        });
    });

    // Search functionality
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
                                    const link = document.createElement('a');
                                    link.href = `/view/${item.path}`;
                                    link.className = 'search-result-item';
                                    link.textContent = item.title;
                                    searchResults.appendChild(link);
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
            }, 300); // 300ms debounce
        });

        // Hide results when clicking outside
        document.addEventListener('click', (e) => {
            if (searchResults && !searchInput.contains(e.target) && !searchResults.contains(e.target)) {
                searchResults.style.display = 'none';
            }
        });
    }

    // View toggle functionality (List/Grid)
    // Use event delegation for dynamic buttons
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

    // HTMX State preservation
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

    // Mobile Search Modal Logic
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
                                        const link = document.createElement('a');
                                        link.href = `/view/${item.path}`;
                                        link.className = 'search-result-item';

                                        // Title
                                        const titleSpan = document.createElement('div');
                                        titleSpan.textContent = item.title;
                                        titleSpan.style.fontWeight = 'bold';
                                        link.appendChild(titleSpan);

                                        // Path/Meta
                                        const meta = document.createElement('div');
                                        meta.className = 'file-meta';
                                        meta.textContent = item.path;
                                        meta.style.fontSize = '0.8em';
                                        link.appendChild(meta);

                                        // Close modal when result clicked
                                        link.addEventListener('click', closeModal);

                                        modalSearchResults.appendChild(link);
                                    });
                                } else {
                                    const empty = document.createElement('div');
                                    empty.className = 'search-result-empty';
                                    empty.textContent = 'No results found';
                                    modalSearchResults.appendChild(empty);
                                }
                            }
                        });
                }, 300);
            });
        }
    }

    // Help Modal Logic
    const helpOpenBtn = document.getElementById('help-open-btn');
    const helpModal = document.getElementById('help-modal');
    const closeHelpModalBtn = document.getElementById('close-help-modal');

    if (helpModal && closeHelpModalBtn) {
        const helpBtns = [
            document.getElementById('help-open-btn'),
            document.getElementById('help-open-btn-mobile')
        ].filter(btn => btn !== null);

        helpBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                helpModal.classList.add('active');
                document.body.classList.add('no-scroll'); // Lock scroll
            });
        });

        const closeHelp = () => {
            helpModal.classList.remove('active');
            document.body.classList.remove('no-scroll'); // Unlock scroll
        };

        closeHelpModalBtn.addEventListener('click', closeHelp);

        helpModal.addEventListener('click', (e) => {
            if (e.target === helpModal) {
                closeHelp();
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && helpModal.classList.contains('active')) {
                closeHelp();
            }
            if ((e.key === '/' || e.key === 's') && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
                // Keep existing search focus or handle s key
            }
        });

        // Help Modal Tabs logic
        const helpTabs = document.querySelectorAll('.help-tab');
        const helpPanels = document.querySelectorAll('.help-panel');

        if (helpTabs.length > 0 && helpPanels.length > 0) {
            helpTabs.forEach(tab => {
                tab.addEventListener('click', () => {
                    const targetTab = tab.dataset.tab;

                    // Update tabs
                    helpTabs.forEach(t => t.classList.toggle('active', t === tab));

                    // Update panels
                    helpPanels.forEach(panel => {
                        panel.classList.toggle('active', panel.id === `help-panel-${targetTab}`);
                    });
                });
            });
        }
    }

    // Sidebar Logic (Toggle, Tabs, TOC)
    const sidebar = document.getElementById('sidebar');
    const sidebarToggleBtns = document.querySelectorAll('.sidebar-toggle-btn');
    const sidebarOverlay = document.getElementById('sidebar-overlay');

    // 1. Sidebar Toggle & Persistence
    if (sidebar) {
        function toggleSidebar() {
            // Use matchMedia to ensure consistency with CSS media queries
            if (window.matchMedia('(max-width: 768px)').matches) {
                // Mobile: Toggle Overlay/Active
                sidebar.classList.toggle('active');
                if (sidebarOverlay) sidebarOverlay.classList.toggle('active');
            } else {
                // Desktop: Toggle Collapsed on HTML element
                document.documentElement.classList.toggle('sidebar-collapsed');
                const isCollapsed = document.documentElement.classList.contains('sidebar-collapsed');
                localStorage.setItem('sidebarCollapsed', isCollapsed);

                // Dispatch resize event for charts/graphs
                window.dispatchEvent(new Event('resize'));
            }
        }

        // Specific Mobile Toggle Logic for Robustness
        const mobileToggleBtn = document.getElementById('sidebar-toggle-mobile');
        if (mobileToggleBtn) {
            const handleMobileClick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                // Force toggle
                sidebar.classList.toggle('active');
                if (sidebarOverlay) sidebarOverlay.classList.toggle('active');

                // Body scroll toggle
                if (sidebar.classList.contains('active')) {
                    document.body.style.overflow = 'hidden';
                } else {
                    document.body.style.overflow = '';
                }
            };

            // Remove existing listeners if any (by cloning? No, just add fresh)
            // Note: The generic listener might still be attached, but preventDefault helps.
            mobileToggleBtn.addEventListener('click', handleMobileClick);
            mobileToggleBtn.addEventListener('touchstart', handleMobileClick, { passive: false });
        }

        // Keep generic logic for desktop, but ensure mobile button doesn't double-fire
        // The generic loop below skips nothing, so we rely on stopPropagation above.

        if (sidebarToggleBtns.length > 0) {
            sidebarToggleBtns.forEach(btn => {
                if (btn.id !== 'sidebar-toggle-mobile') {
                    btn.addEventListener('click', toggleSidebar);
                }
            });
        }

        if (sidebarOverlay) {
            sidebarOverlay.addEventListener('click', () => {
                sidebar.classList.remove('active');
                if (sidebarOverlay) sidebarOverlay.classList.remove('active');
                document.body.style.overflow = '';
            });
        }
    }

    // 2. Sidebar Tabs
    const tabButtons = document.querySelectorAll('.sidebar-tab');
    const tabPanels = document.querySelectorAll('.sidebar-panel');

    if (tabButtons.length > 0 && tabPanels.length > 0) {
        tabButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                // Deactivate all
                tabButtons.forEach(b => b.classList.remove('active'));
                tabPanels.forEach(p => p.classList.remove('active'));

                // Activate clicked
                btn.classList.add('active');
                const tabName = btn.dataset.tab;
                const panel = document.getElementById(`sidebar-${tabName}`);
                if (panel) panel.classList.add('active');
            });
        });
    }

    // 3. TOC Generator (Nested Tree for Outline)
    function generateTOC() {
        const outlineContainer = document.getElementById('sidebar-outline');
        const content = document.querySelector('.markdown-body');

        if (!outlineContainer || !content) return;

        const headers = Array.from(content.querySelectorAll('h1, h2, h3'));

        if (headers.length === 0) {
            outlineContainer.innerHTML = '<div class="toc-empty">No headers found</div>';
            return;
        }

        const rootUl = document.createElement('ul');
        rootUl.className = 'toc-tree';

        // Stack to keep track of the current nesting path
        // [{ level: 0, container: rootUl }]
        // Level 0 is a dummy root
        const stack = [{ level: 0, container: rootUl }];

        headers.forEach((header, index) => {
            // Add ID if missing for anchoring
            if (!header.id) {
                header.id = `toc-${index}`;
            }

            const level = parseInt(header.tagName.substring(1));
            const text = header.textContent;

            // Find the correct parent in the stack
            // Pop until we find a level strictly less than current header level
            while (stack.length > 0 && stack[stack.length - 1].level >= level) {
                stack.pop();
            }

            // The last item in stack is now the parent
            const parent = stack[stack.length - 1];

            // Create list item
            const li = document.createElement('li');
            li.className = 'toc-item-wrapper';

            // Create the content div
            const contentDiv = document.createElement('div');
            contentDiv.className = `toc-item toc-h${level}`;
            contentDiv.onclick = (e) => {
                e.stopPropagation();
                // Close sidebar on TOC selection (Mobile Only)
                if (window.innerWidth <= 768) {
                    sidebar.classList.remove('active');
                    if (sidebarOverlay) sidebarOverlay.classList.remove('active');
                }

                header.scrollIntoView({ behavior: 'smooth', block: 'start' });

                // Highlight active
                document.querySelectorAll('.toc-item').forEach(i => i.classList.remove('active'));
                contentDiv.classList.add('active');
            };

            // Icon
            const iconSpan = document.createElement('span');
            iconSpan.className = 'toc-icon';
            if (level <= 2) {
                iconSpan.textContent = 'H';
                iconSpan.classList.add('type-header');
            } else {
                iconSpan.innerHTML = '&#9670;'; // Diamond
                iconSpan.classList.add('type-item');
            }

            // Text
            const textSpan = document.createElement('span');
            textSpan.className = 'toc-text';
            textSpan.textContent = text;

            contentDiv.appendChild(iconSpan);
            contentDiv.appendChild(textSpan);
            li.appendChild(contentDiv);

            // Container for children
            const childUl = document.createElement('ul');
            childUl.className = 'toc-sublist';
            li.appendChild(childUl);

            // Append to parent container
            parent.container.appendChild(li);

            // Push this new container to stack
            stack.push({ level: level, container: childUl });
        });

        outlineContainer.innerHTML = '';
        outlineContainer.appendChild(rootUl);
    }

    // Run TOC generation after a slight delay
    setTimeout(generateTOC, 100);

    // 4. Auto-close sidebar on File Link click
    const fileLinks = document.querySelectorAll('.tree-file');
    fileLinks.forEach(link => {
        link.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                sidebar.classList.remove('active');
                if (sidebarOverlay) sidebarOverlay.classList.remove('active');
            }
        });
    });

    // Link Preview Logic
    const previewCache = new Map();
    let previewTooltip = null;
    let hideTimeout = null;
    let activeLink = null;
    let previewRequestId = 0;

    function createPreviewTooltip() {
        if (previewTooltip) return previewTooltip;

        const tooltip = document.createElement('div');
        tooltip.className = 'preview-tooltip';
        tooltip.innerHTML = '<div class="preview-loading">読み込み中...</div>';
        document.body.appendChild(tooltip);

        // Keep tooltip alive when hovering over it
        tooltip.addEventListener('mouseenter', () => {
            if (hideTimeout) {
                clearTimeout(hideTimeout);
                hideTimeout = null;
            }
        });

        tooltip.addEventListener('mouseleave', () => {
            hidePreview();
        });

        return tooltip;
    }

    function showPreview(link, path) {
        const requestId = ++previewRequestId;

        if (hideTimeout) {
            clearTimeout(hideTimeout);
            hideTimeout = null;
        }

        activeLink = link;
        previewTooltip = createPreviewTooltip();
        previewTooltip.dataset.activePath = path;

        // Show immediately and position
        previewTooltip.classList.add('active');
        updateTooltipPosition(link);

        if (previewCache.has(path)) {
            renderPreviewContent(previewCache.get(path), link, requestId);
        } else {
            previewTooltip.innerHTML = '<div class="preview-loading">読み込み中...</div>';
            fetch(`/api/preview?path=${encodeURIComponent(path)}`)
                .then(res => {
                    if (!res.ok) throw new Error('Failed to load');
                    return res.json();
                })
                .then(data => {
                    if (requestId !== previewRequestId) return;
                    previewCache.set(path, data);
                    renderPreviewContent(data, link, requestId);
                })
                .catch(err => {
                    if (requestId !== previewRequestId) return;
                    previewTooltip.innerHTML = '<div class="preview-error">プレビューを表示できませんでした</div>';
                });
        }
    }

    function renderPreviewContent(data, link, requestId) {
        if (!previewTooltip || requestId !== previewRequestId) return;
        previewTooltip.innerHTML = `
            <div class="preview-header">
                <span class="preview-title">${data.title}</span>
            </div>
            <div class="preview-content markdown-body">${data.content}</div>
        `;
        if (link) {
            updateTooltipPosition(link);
        }
    }

    function updateTooltipPosition(link) {
        if (!previewTooltip) return;
        const rect = link.getBoundingClientRect();
        const tooltipRect = previewTooltip.getBoundingClientRect();
        const gap = 12;

        let top;
        // Default to TOP (Above), only flip to BOTTOM if it hits the top edge of viewport
        top = rect.top - tooltipRect.height - gap;
        if (top < 10) {
            top = rect.bottom + gap;
        }

        let left = rect.left;
        // Keep within viewport width
        if (left + tooltipRect.width > window.innerWidth - 20) {
            left = window.innerWidth - tooltipRect.width - 20;
        }
        if (left < 10) left = 10;

        previewTooltip.style.top = `${top + window.scrollY}px`;
        previewTooltip.style.left = `${left + window.scrollX}px`;
    }

    function hidePreview(delay = 300) {
        if (hideTimeout) clearTimeout(hideTimeout);

        hideTimeout = setTimeout(() => {
            if (previewTooltip) {
                previewTooltip.remove();
                previewTooltip = null;
            }
            activeLink = null;
        }, delay);
    }

    // Use a single delegated listener for stability
    document.addEventListener('mouseover', (e) => {
        const link = e.target.closest('a');

        // Internal link check: Only trigger within markdown content or existing tooltips
        const isInternalLink = link &&
            (link.closest('.markdown-body') || link.closest('.preview-tooltip')) &&
            !link.classList.contains('toc-item') &&
            !link.closest('.toc-tree') &&
            !link.closest('.settings-modal');

        if (isInternalLink) {
            if (activeLink === link) return; // Same link, do nothing

            const href = link.getAttribute('href');
            if (!href || href.startsWith('http') || href.startsWith('#') || href.startsWith('javascript:')) {
                hidePreview(100);
                return;
            }

            // Path Resolution
            let path = '';
            if (href.startsWith('/view/')) {
                path = href.substring(6);
            } else if (!href.startsWith('/')) {
                const currentPath = window.location.pathname;
                if (currentPath.startsWith('/view/')) {
                    const currentDir = currentPath.substring(6, currentPath.lastIndexOf('/') + 1);
                    path = currentDir + href;
                }
            }

            if (path) {
                path = decodeURIComponent(path);
                showPreview(link, path);
            }
        } else {
            // Check if we are over the tooltip itself
            if (!e.target.closest('.preview-tooltip')) {
                if (activeLink) {
                    hidePreview();
                }
            }
        }
    });

    // Settings Logic
    function initSettings() {
        const settingsModal = document.getElementById('settings-modal');
        const openBtns = [
            document.getElementById('settings-open-btn'),
            document.getElementById('settings-open-btn-mobile')
        ].filter(btn => btn !== null);
        const closeBtn = document.getElementById('close-settings-modal');

        if (settingsModal && openBtns.length > 0 && closeBtn) {
            openBtns.forEach(btn => {
                btn.addEventListener('click', () => {
                    settingsModal.classList.add('active');
                });
            });
        }

        // Inputs
        const fontSizeSelect = document.getElementById('setting-font-size');
        const readableWidthCheck = document.getElementById('setting-readable-width');
        const lineNumbersCheck = document.getElementById('setting-line-numbers');
        const codeThemeSelect = document.getElementById('setting-code-theme'); // New
        const themeModeSelect = document.getElementById('setting-theme-select'); // Fixed ID
        const mermaidThemeSelect = document.getElementById('setting-mermaid-theme');
        const rebuildIndexBtn = document.getElementById('rebuild-index-btn'); // New
        const clearCacheBtn = document.getElementById('clear-cache-btn'); // New

        // State defaults
        const defaults = {
            fontSize: 'medium',
            readableWidth: true,
            lineNumbers: false,
            codeTheme: 'github-dark', // New
            mermaidTheme: 'default'
        };

        // Load Settings
        const loadSettings = () => {
            const savedFontSize = localStorage.getItem('fontSize') || defaults.fontSize;
            const savedReadableWidth = localStorage.getItem('readableWidth');
            const isReadableWidth = savedReadableWidth === null ? defaults.readableWidth : (savedReadableWidth === 'true');
            const savedLineNumbers = localStorage.getItem('lineNumbers');
            const isLineNumbers = savedLineNumbers === null ? defaults.lineNumbers : (savedLineNumbers === 'true');

            const savedCodeTheme = localStorage.getItem('codeTheme') || defaults.codeTheme;
            const currentTheme = localStorage.getItem('theme') || 'dark';
            const savedMermaidTheme = localStorage.getItem('mermaidTheme') || defaults.mermaidTheme;

            // Apply to inputs
            if (fontSizeSelect) fontSizeSelect.value = savedFontSize;
            if (readableWidthCheck) readableWidthCheck.checked = isReadableWidth;
            if (lineNumbersCheck) lineNumbersCheck.checked = isLineNumbers;
            if (codeThemeSelect) codeThemeSelect.value = savedCodeTheme;
            if (themeModeSelect) themeModeSelect.value = currentTheme;
            if (mermaidThemeSelect) mermaidThemeSelect.value = savedMermaidTheme;

            // Apply to App
            applySettings({
                fontSize: savedFontSize,
                readableWidth: isReadableWidth,
                lineNumbers: isLineNumbers,
                codeTheme: savedCodeTheme,
                theme: currentTheme
                // mermaidTheme is applied by initMermaid (needs reload or re-init)
            });
        };

        const applySettings = (settings) => {
            // Font Size
            document.body.classList.remove('font-small', 'font-medium', 'font-large');
            document.body.classList.add(`font-${settings.fontSize}`);

            // Readable Width
            if (settings.readableWidth) {
                document.body.classList.add('readable-width');
            } else {
                document.body.classList.remove('readable-width');
            }

            // Line Numbers
            const codes = document.querySelectorAll('pre code');
            codes.forEach(code => {
                const pre = code.parentElement;
                if (settings.lineNumbers) {
                    pre.classList.add('line-numbers');
                    if (!pre.querySelector('.line-number-rows')) {
                        const text = code.textContent;
                        // Fix: Trim trailing newline to avoid extra line number
                        const cleanText = text.length > 0 && text[text.length - 1] === '\n' ? text.slice(0, -1) : text;
                        const lineCount = cleanText.split('\n').length;
                        const rows = document.createElement('span');
                        rows.className = 'line-number-rows';
                        // Generate empty spans for counters
                        let spans = '';
                        for (let i = 0; i < lineCount; i++) spans += '<span></span>';
                        rows.innerHTML = spans;
                        pre.appendChild(rows);
                    }
                } else {
                    pre.classList.remove('line-numbers');
                }
            });

            // Code Theme
            if (settings.codeTheme) {
                const codeThemes = ['github-dark', 'github', 'monokai', 'dracula'];
                codeThemes.forEach(t => document.body.classList.remove(`code-theme-${t}`));
                document.body.classList.add(`code-theme-${settings.codeTheme}`);

                if (typeof window.updateHighlightTheme === 'function') {
                    window.updateHighlightTheme(settings.codeTheme);
                }
            }

            // Theme (Mode)
            if (settings.theme) {
                document.documentElement.setAttribute('data-theme', settings.theme);
            }
        };

        // Event Listeners (Moved inside initial check)
        if (settingsModal && openBtns.length > 0 && closeBtn) {
            openBtns.forEach(btn => {
                btn.addEventListener('click', () => {
                    settingsModal.classList.add('active');
                    document.body.classList.add('no-scroll'); // Lock scroll
                });
            });

            closeBtn.addEventListener('click', () => {
                settingsModal.classList.remove('active');
                document.body.classList.remove('no-scroll'); // Unlock scroll
            });
        }

        if (settingsModal) {
            settingsModal.addEventListener('click', (e) => {
                if (e.target === settingsModal) {
                    settingsModal.classList.remove('active');
                    document.body.classList.remove('no-scroll'); // Unlock scroll
                }
            });
        }

        // Tab Navigation
        const settingsNavItems = document.querySelectorAll('.settings-nav-item');
        const settingsTabPanes = document.querySelectorAll('.settings-tab-pane');

        settingsNavItems.forEach(item => {
            item.addEventListener('click', () => {
                const targetTab = item.getAttribute('data-tab');

                // Update Nav Items
                settingsNavItems.forEach(nav => nav.classList.remove('active'));
                item.classList.add('active');

                // Update Tab Panes
                settingsTabPanes.forEach(pane => {
                    if (pane.id === `settings-tab-${targetTab}`) {
                        pane.classList.add('active');
                    } else {
                        pane.classList.remove('active');
                    }
                });
            });
        });

        // Change Handlers
        if (fontSizeSelect) {
            fontSizeSelect.addEventListener('change', (e) => {
                const val = e.target.value;
                localStorage.setItem('fontSize', val);
                document.body.classList.remove('font-small', 'font-medium', 'font-large');
                document.body.classList.add(`font-${val}`);
            });
        }

        if (readableWidthCheck) {
            readableWidthCheck.addEventListener('change', (e) => {
                const val = e.target.checked;
                localStorage.setItem('readableWidth', val);
                if (val) document.body.classList.add('readable-width');
                else document.body.classList.remove('readable-width');
            });
        }

        if (lineNumbersCheck) {
            lineNumbersCheck.addEventListener('change', (e) => {
                const val = e.target.checked;
                localStorage.setItem('lineNumbers', val);
                // Re-apply to all blocks
                const codes = document.querySelectorAll('pre code');
                codes.forEach(code => {
                    const pre = code.parentElement;
                    if (val) {
                        pre.classList.add('line-numbers');
                        if (!pre.querySelector('.line-number-rows')) {
                            const text = code.textContent;
                            // Fix: Trim trailing newline to avoid extra line number
                            const cleanText = text.length > 0 && text[text.length - 1] === '\n' ? text.slice(0, -1) : text;
                            const lineCount = cleanText.split('\n').length;

                            const rows = document.createElement('span');
                            rows.className = 'line-number-rows';
                            let spans = '';
                            for (let i = 0; i < lineCount; i++) spans += '<span></span>';
                            rows.innerHTML = spans;
                            pre.appendChild(rows);
                        }
                    } else {
                        pre.classList.remove('line-numbers');
                        // Remove the rows element
                        const rows = pre.querySelector('.line-number-rows');
                        if (rows) {
                            rows.remove();
                        }
                    }
                });
            });
        }

        if (codeThemeSelect) {
            codeThemeSelect.addEventListener('change', (e) => {
                const val = e.target.value;
                localStorage.setItem('codeTheme', val);
                // Remove old
                const codeThemes = ['github-dark', 'github', 'monokai', 'dracula'];
                codeThemes.forEach(t => document.body.classList.remove(`code-theme-${t}`));
                document.body.classList.add(`code-theme-${val}`);

                // Fix: Actually update the stylesheet!
                if (typeof window.updateHighlightTheme === 'function') {
                    window.updateHighlightTheme(val);
                }
            });
        }

        if (themeModeSelect) {
            themeModeSelect.addEventListener('change', (e) => {
                const val = e.target.value;

                // Function to update the DOM
                const updateTheme = () => {
                    localStorage.setItem('theme', val);
                    document.documentElement.setAttribute('data-theme', val);

                    // Update highlight.js theme dynamically
                    if (typeof updateHighlightTheme === 'function') updateHighlightTheme(val);
                };

                // Use View Transitions API if supported
                if (document.startViewTransition) {
                    document.startViewTransition(() => {
                        updateTheme();
                    });
                } else {
                    // Fallback
                    updateTheme();
                }

                // For Mermaid, we need to check if we can re-render without reload.
                // If the mermaid theme is set to 'default', it needs to react to the main theme change.
                const savedMermaidTheme = localStorage.getItem('mermaidTheme') || 'default';
                if (savedMermaidTheme === 'default') {
                    if (typeof window.updateMermaidConfig === 'function') {
                        // Update without reload!
                        window.updateMermaidConfig();
                    }
                }
            });
        }

        if (mermaidThemeSelect) {
            mermaidThemeSelect.addEventListener('change', (e) => {
                const val = e.target.value;
                localStorage.setItem('mermaidTheme', val);

                if (typeof window.updateMermaidConfig === 'function') {
                    window.updateMermaidConfig();
                } else {
                    // Fallback if something is wrong
                    sessionStorage.setItem('settingsModalOpen', 'true');
                    location.reload();
                }
            });
        }

        // Advanced Actions
        if (rebuildIndexBtn) {
            rebuildIndexBtn.addEventListener('click', () => {
                if (confirm("インデックスを再構築しますか？\n（時間がかかる場合があります）")) {
                    rebuildIndexBtn.disabled = true;
                    rebuildIndexBtn.textContent = '処理中...';

                    fetch('/api/rebuild-index', { method: 'POST' })
                        .then(res => {
                            if (res.ok) {
                                showToast("インデックスを再構築しました", "success");
                                setTimeout(() => location.reload(), 1500);
                            } else {
                                showToast("再構築に失敗しました", "error");
                            }
                        })
                        .catch(err => {
                            console.error(err);
                            showToast("エラーが発生しました", "error");
                        })
                        .finally(() => {
                            rebuildIndexBtn.disabled = false;
                            rebuildIndexBtn.textContent = '再構築'; // Or restore previous text
                        });
                }
            });
        }

        if (clearCacheBtn) {
            clearCacheBtn.addEventListener('click', () => {
                if (confirm("キャッシュとローカル設定をクリアしますか？\n（ページがリロードされます）")) {
                    localStorage.clear();
                    sessionStorage.clear();
                    location.reload();
                }
            });
        }

        // Init
        loadSettings();
    }

    // Moved INIT to end of file to ensure all functions are defined
    // initSettings();

    // Check if we need to reopen settings modal (after theme reload)
    if (sessionStorage.getItem('settingsModalOpen') === 'true') {
        const settingsModal = document.getElementById('settings-modal');
        if (settingsModal) {
            settingsModal.classList.add('active');
            document.body.classList.add('no-scroll'); // Re-lock scroll
        }
        sessionStorage.removeItem('settingsModalOpen');
    }

    // Initialize Highlight.js
    if (window.hljs) {
        console.log('Highlight.js found, initializing...');
        hljs.highlightAll();

        // Fix: Promote .hljs class to <pre> to ensure background covers the whole block
        // and fix gap issues with padding.
        document.querySelectorAll('pre code.hljs').forEach(block => {
            if (block.parentElement && block.parentElement.tagName === 'PRE') {
                block.parentElement.classList.add('hljs');
                // Remove generic class if it conflicts? No, let it stack.
            }
        });
        console.log('Highlight.js applied to blocks.');
    } else {
        console.error('Highlight.js not found! Check network or script tag.');
    }

    // Function to update Highlight.js theme
    // Function to update Highlight.js theme
    window.updateHighlightTheme = (themeName) => {
        const link = document.getElementById('highlight-theme');
        if (!link) {
            console.error('Highlight.js theme link not found!');
            return;
        }

        // Map internal names to local files
        const themeMap = {
            'github-dark': 'github-dark.min.css',
            'github': 'github.min.css',
            'monokai': 'monokai.min.css',
            'dracula': 'dracula.min.css'
        };

        const themeFile = themeMap[themeName] || 'github-dark.min.css';
        const newUrl = `/static/css/themes/${themeFile}`;

        console.log(`Switching code theme to: ${themeName}`);
        console.log(`URL: ${newUrl}`);
        link.href = newUrl;
    };

    // Accordion Animation Logic
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

    // --- File Sync Logic (Localhost Only) ---
    function initSyncSettings() {
        const syncTabBtn = document.querySelector('[data-tab="files"]');
        if (!syncTabBtn) return; // Not localhost or not present

        const enabledToggle = document.getElementById('setting-sync-enabled');
        const autoSyncToggle = document.getElementById('setting-auto-sync-enabled');
        const contentSrcInput = document.getElementById('setting-content-src');
        const imagesSrcInput = document.getElementById('setting-images-src');
        const baseUrlInput = document.getElementById('setting-base-url');
        const intervalSelect = document.getElementById('setting-sync-interval');
        const intervalWrapper = document.getElementById('auto-sync-interval-wrapper');
        const wrapper = document.getElementById('sync-settings-wrapper');
        const saveBtn = document.getElementById('save-sync-settings-btn');
        const manualSyncBtn = document.getElementById('manual-sync-btn');
        const lastSyncLabel = document.getElementById('last-sync-time');

        let currentConfig = {};

        // Load Config
        fetch('/api/sync/config')
            .then(res => res.json())
            .then(config => {
                currentConfig = config;
                enabledToggle.checked = config.sync_enabled;
                autoSyncToggle.checked = config.auto_sync_enabled;
                contentSrcInput.value = config.content_src || '';
                imagesSrcInput.value = config.images_src || '';
                if (baseUrlInput) baseUrlInput.value = config.base_url || '';
                intervalSelect.value = config.interval_minutes || 60;
                lastSyncLabel.textContent = config.last_sync ? `最終同期: ${config.last_sync}` : '';

                toggleInputs(config.sync_enabled);
                toggleAutoSyncInputs(config.auto_sync_enabled);
            })
            .catch(err => console.error("Failed to load sync config", err));

        // Toggle Visibility (Accordion)
        function toggleInputs(enabled) {
            wrapper.style.display = enabled ? 'block' : 'none';
        }

        function toggleAutoSyncInputs(autoEnabled) {
            intervalWrapper.style.display = autoEnabled ? 'block' : 'none';
        }

        enabledToggle.addEventListener('change', () => {
            toggleInputs(enabledToggle.checked);
        });

        autoSyncToggle.addEventListener('change', () => {
            toggleAutoSyncInputs(autoSyncToggle.checked);
        });

        // Save Button Handler
        if (saveBtn) {
            saveBtn.addEventListener('click', () => {
                const confirmed = confirm("この設定を保存してもよろしいですか？");
                if (confirmed) {
                    saveConfig();
                }
            });
        }

        function clearErrors() {
            document.querySelectorAll('.setting-error').forEach(el => {
                el.textContent = '';
                el.style.display = 'none';
                el.classList.remove('warning'); // Clear warning state
            });
        }

        function saveConfig() {
            clearErrors();
            const config = {
                sync_enabled: enabledToggle.checked,
                auto_sync_enabled: autoSyncToggle.checked,
                content_src: contentSrcInput.value,
                images_src: imagesSrcInput.value,
                base_url: baseUrlInput ? baseUrlInput.value.trim() : '',
                interval_minutes: parseInt(intervalSelect.value),
                last_sync: "" // Server handles this
            };

            fetch('/api/sync/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            })
                .then(async res => {
                    const data = await res.json();
                    if (res.ok) {
                        showToast(MESSAGES.system?.S001 || "設定を保存しました", "success");
                        if (data.warnings) {
                            Object.keys(data.warnings).forEach(key => {
                                const errorEl = document.getElementById(`${key}-error`);
                                if (errorEl) {
                                    errorEl.textContent = data.warnings[key];
                                    errorEl.style.display = 'block';
                                    errorEl.classList.add('warning'); // Use CSS class for warnings
                                }
                            });
                        }
                    } else if (res.status === 400 && data.errors) {
                        // Display validation errors
                        Object.keys(data.errors).forEach(key => {
                            const errorEl = document.getElementById(`${key}-error`);
                            if (errorEl) {
                                errorEl.textContent = data.errors[key];
                                errorEl.style.display = 'block';
                            }
                        });
                        showToast(MESSAGES.errors?.E003 || "入力内容に誤りがあります", "error");
                    } else {
                        throw new Error("Save failed");
                    }
                })
                .catch(err => {
                    console.error("Failed to save config", err);
                    showToast(MESSAGES.errors?.E004 || "設定の保存に失敗しました", "error");
                });
        }

        // --- Directory Browser Logic ---
        const dirModal = document.getElementById('dir-browser-modal');
        const dirList = document.getElementById('dir-browser-list');
        const dirCurrentPathLabel = document.getElementById('dir-current-path');
        const dirSelectBtn = document.getElementById('select-dir-btn');
        const dirCloseBtn = document.getElementById('close-dir-browser-modal');
        const browseBtns = document.querySelectorAll('.browser-dir-btn');

        let currentActiveInput = null;
        let selectedDirPath = null;

        function openDirBrowser(targetInputId) {
            currentActiveInput = document.getElementById(targetInputId);
            selectedDirPath = currentActiveInput.value || '/';
            // If it's a Windows path in Docker, it might fail, so default to /mnt/host_data if it exists
            if (selectedDirPath.includes(':') || selectedDirPath === '') {
                selectedDirPath = '/';
            }
            dirModal.classList.add('active');
            loadDirs(selectedDirPath);
        }

        async function loadDirs(path) {
            dirList.innerHTML = '<div class="loading-spinner">読み込み中...</div>';
            try {
                const res = await fetch(`/api/list-dirs?path=${encodeURIComponent(path)}`);
                const data = await res.json();
                if (res.ok) {
                    renderDirList(data);
                } else {
                    dirList.innerHTML = `<div class="error-msg">${data.message || 'フォルダの取得に失敗しました'}</div>`;
                }
            } catch (err) {
                console.error("Failed to load dirs", err);
                dirList.innerHTML = '<div class="error-msg">通信エラーが発生しました</div>';
            }
        }

        function renderDirList(data) {
            dirList.innerHTML = '';
            dirCurrentPathLabel.textContent = data.current;
            selectedDirPath = data.current;

            // Parent Dir
            if (data.parent) {
                const item = document.createElement('div');
                item.className = 'dir-item parent-dir';
                item.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 17l-5-5 5-5M18 12H6"/></svg>
                    <span>.. (親フォルダへ)</span>
                `;
                item.onclick = () => loadDirs(data.parent);
                dirList.appendChild(item);
            }

            // Subdirs
            data.dirs.forEach(dir => {
                const item = document.createElement('div');
                item.className = 'dir-item';
                item.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                    <span>${dir.name}</span>
                `;
                item.onclick = () => loadDirs(dir.path);
                dirList.appendChild(item);
            });

            if (data.dirs.length === 0 && !data.parent) {
                dirList.innerHTML = '<div class="empty-msg">ディレクトリが見つかりませんでした</div>';
            }
        }

        browseBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                openDirBrowser(btn.dataset.target);
            });
        });

        dirCloseBtn.onclick = () => dirModal.classList.remove('active');

        dirSelectBtn.onclick = () => {
            if (currentActiveInput && selectedDirPath) {
                currentActiveInput.value = selectedDirPath;
                dirModal.classList.remove('active');
            }
        };

        // Manual Sync Logic (rest of the code)
        manualSyncBtn.addEventListener('click', () => {
            if (!confirm("ファイルと画像の同期を今すぐ実行しますか？")) return;

            manualSyncBtn.classList.add('loading');
            manualSyncBtn.disabled = true;

            fetch('/api/sync', { method: 'POST' })
                .then(async res => {
                    const data = await res.json();
                    if (res.ok) {
                        lastSyncLabel.textContent = `最終同期: ${data.last_sync}`;
                        showToast("同期が完了しました", "success");
                    } else {
                        throw new Error(data.message || "Sync failed");
                    }
                })
                .catch(err => {
                    console.error("Sync failed", err);
                    showToast(`同期に失敗しました: ${err.message}`, "error");
                })
                .finally(() => {
                    manualSyncBtn.classList.remove('loading');
                    manualSyncBtn.disabled = false;
                });
        });
    }

    // --- Toast Notification System ---
    function showToast(message, type = 'info') {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        // Icon based on type
        let icon = '';
        if (type === 'success') icon = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>';
        else if (type === 'error') icon = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>';

        toast.innerHTML = `${icon}<span>${message}</span>`;

        container.appendChild(toast);

        // Animate in
        requestAnimationFrame(() => toast.classList.add('show'));

        // Remove after 3s
        setTimeout(() => {
            toast.classList.remove('show');
            toast.addEventListener('transitionend', () => toast.remove());
        }, 3000);
    }

    // --- Sidebar Resize Logic ---
    function initSidebarResize() {
        const resizer = document.getElementById('sidebar-resizer');
        const sidebar = document.querySelector('.sidebar');
        if (!resizer || !sidebar) return;

        let isResizing = false;

        // Load saved width
        const savedWidth = localStorage.getItem('sidebarWidth');
        if (savedWidth && window.innerWidth > 768) {
            document.documentElement.style.setProperty('--sidebar-width', `${savedWidth}px`);
        }

        resizer.addEventListener('mousedown', (e) => {
            if (window.innerWidth <= 768) return; // Disable on mobile
            isResizing = true;
            document.body.classList.add('resizing');
            resizer.classList.add('resizing');
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;

            // Activity bar is 50px offset
            const activityBarWidth = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--activity-bar-width')) || 50;
            let newWidth = e.clientX - activityBarWidth;

            // Constraints
            if (newWidth < 200) newWidth = 200;
            if (newWidth > 600) newWidth = 600;

            document.documentElement.style.setProperty('--sidebar-width', `${newWidth}px`);
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                document.body.classList.remove('resizing');
                resizer.classList.remove('resizing');

                // Save width
                const currentWidth = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width'));
                localStorage.setItem('sidebarWidth', currentWidth);
            }
        });

        // Handle window resize (reset if mobile)
        window.addEventListener('resize', () => {
            if (window.innerWidth <= 768) {
                document.documentElement.style.removeProperty('--sidebar-width');
            } else {
                const savedWidth = localStorage.getItem('sidebarWidth');
                if (savedWidth) {
                    document.documentElement.style.setProperty('--sidebar-width', `${savedWidth}px`);
                }
            }
        });
    }

    // Initialize
    initSettings();
    initSyncSettings();
    initSidebarResize();

});
