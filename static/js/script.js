document.addEventListener('DOMContentLoaded', () => {
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
                securityLevel: 'loose'
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

    // Task list checkbox rendering
    function renderTaskLists() {
        // Find all list items
        const listItems = document.querySelectorAll('li');

        listItems.forEach((li) => {
            const text = li.textContent.trim();

            // Check for unchecked task: [ ]
            if (text.startsWith('[ ]')) {
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.className = 'task-list-item-checkbox';
                checkbox.disabled = true; // Read-only

                // Replace the [ ] with checkbox
                li.innerHTML = li.innerHTML.replace(/^\s*\[ \]\s*/, '');
                li.insertBefore(checkbox, li.firstChild);
                li.className += ' task-list-item';
            }
            // Check for checked task: [x] or [X]
            else if (text.startsWith('[x]') || text.startsWith('[X]')) {
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.className = 'task-list-item-checkbox';
                checkbox.checked = true;
                checkbox.disabled = true; // Read-only

                // Replace the [x] with checkbox
                li.innerHTML = li.innerHTML.replace(/^\s*\[[xX]\]\s*/, '');
                li.insertBefore(checkbox, li.firstChild);
                li.className += ' task-list-item';
            }
        });
    }

    // Render task lists after page load
    renderTaskLists();

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
    const listViewBtn = document.getElementById('list-view-btn');
    const gridViewBtn = document.getElementById('grid-view-btn');
    const fileList = document.querySelector('.file-list');

    if (listViewBtn && gridViewBtn && fileList) {
        // Load saved view preference from localStorage
        const savedView = localStorage.getItem('fileListView') || 'list';

        function setView(view) {
            if (view === 'grid') {
                fileList.classList.add('grid-view');
                listViewBtn.classList.remove('active');
                gridViewBtn.classList.add('active');
            } else {
                fileList.classList.remove('grid-view');
                listViewBtn.classList.add('active');
                gridViewBtn.classList.remove('active');
            }
            localStorage.setItem('fileListView', view);
        }

        // Set initial view
        setView(savedView);

        // Button click handlers
        listViewBtn.addEventListener('click', () => {
            setView('list');
        });
        gridViewBtn.addEventListener('click', () => {
            setView('grid');
        });
    }

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
            setTimeout(() => {
                if (modalSearchInput) modalSearchInput.focus();
            }, 100);
        });

        // Close Modal
        const closeModal = () => {
            searchModal.classList.remove('active');
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

    function createPreviewTooltip() {
        if (previewTooltip) return previewTooltip;

        const tooltip = document.createElement('div');
        tooltip.className = 'preview-tooltip';
        tooltip.innerHTML = '<div class="preview-loading">Loading...</div>';
        document.body.appendChild(tooltip);
        return tooltip;
    }

    function showPreview(link, path) {
        if (hideTimeout) {
            clearTimeout(hideTimeout);
            hideTimeout = null;
        }

        if (previewTooltip && previewTooltip.dataset.activePath !== path) {
            hidePreview(0);
        }

        previewTooltip = createPreviewTooltip();
        updateTooltipPosition(link);

        if (previewCache.has(path)) {
            renderPreviewContent(previewCache.get(path), link);
        } else {
            previewTooltip.innerHTML = '<div class="preview-loading">Loading...</div>';
            fetch(`/api/preview?path=${encodeURIComponent(path)}`)
                .then(res => {
                    if (!res.ok) throw new Error('Failed to load');
                    return res.json();
                })
                .then(data => {
                    previewCache.set(path, data);
                    if (previewTooltip && previewTooltip.dataset.activePath === path) {
                        renderPreviewContent(data, link);
                    }
                })
                .catch(err => {
                    if (previewTooltip && previewTooltip.dataset.activePath === path) {
                        previewTooltip.innerHTML = '<div class="preview-error">Failed to load preview</div>';
                    }
                });
        }

        previewTooltip.classList.add('active');
        previewTooltip.dataset.activePath = path;

        previewTooltip.addEventListener('mouseenter', () => {
            if (hideTimeout) {
                clearTimeout(hideTimeout);
                hideTimeout = null;
            }
        });

        previewTooltip.addEventListener('mouseleave', () => {
            hidePreview();
        });
    }

    function renderPreviewContent(data, link) {
        if (!previewTooltip) return;
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
        const gap = 10;
        let top = rect.top - tooltipRect.height - gap;
        let left = rect.left;

        if (top < 10) {
            top = rect.bottom + gap;
        }
        if (left + 400 > window.innerWidth) {
            left = window.innerWidth - 410;
        }

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
        }, delay);
    }

    document.addEventListener('mouseover', (e) => {
        const link = e.target.closest('a');
        if (link && !link.classList.contains('toc-item') && !link.closest('.toc-tree')) {
            // Basic link hover logic if needed
        }
    });

    // Settings Logic
    function initSettings() {
        const settingsModal = document.getElementById('settings-modal');
        const openBtn = document.getElementById('settings-open-btn');
        const closeBtn = document.getElementById('close-settings-modal');

        // Inputs
        const fontSizeSelect = document.getElementById('setting-font-size');
        const readableWidthCheck = document.getElementById('setting-readable-width');
        const lineNumbersCheck = document.getElementById('setting-line-numbers');
        const themeModeSelect = document.getElementById('setting-theme-mode');
        const mermaidThemeSelect = document.getElementById('setting-mermaid-theme');

        // State defaults
        const defaults = {
            fontSize: 'medium',
            readableWidth: true,
            lineNumbers: false,
            mermaidTheme: 'default'
        };

        // Load Settings
        const loadSettings = () => {
            const savedFontSize = localStorage.getItem('fontSize') || defaults.fontSize;
            const savedReadableWidth = localStorage.getItem('readableWidth');
            const isReadableWidth = savedReadableWidth === null ? defaults.readableWidth : (savedReadableWidth === 'true');
            const savedLineNumbers = localStorage.getItem('lineNumbers');
            const isLineNumbers = savedLineNumbers === null ? defaults.lineNumbers : (savedLineNumbers === 'true');

            const currentTheme = localStorage.getItem('theme') || 'dark';
            const savedMermaidTheme = localStorage.getItem('mermaidTheme') || defaults.mermaidTheme;

            // Apply to inputs
            if (fontSizeSelect) fontSizeSelect.value = savedFontSize;
            if (readableWidthCheck) readableWidthCheck.checked = isReadableWidth;
            if (lineNumbersCheck) lineNumbersCheck.checked = isLineNumbers;
            if (themeModeSelect) themeModeSelect.value = currentTheme;
            if (mermaidThemeSelect) mermaidThemeSelect.value = savedMermaidTheme;

            // Apply to App
            applySettings({
                fontSize: savedFontSize,
                readableWidth: isReadableWidth,
                lineNumbers: isLineNumbers,
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

            // Theme (Mode)
            if (settings.theme) {
                document.documentElement.setAttribute('data-theme', settings.theme);
                // Also update Highlight.js if needed (separate function)
                if (typeof updateHighlightTheme === 'function') {
                    updateHighlightTheme(settings.theme);
                }
            }
        };

        // Event Listeners
        if (openBtn && settingsModal) {
            openBtn.addEventListener('click', () => {
                settingsModal.classList.add('active');
                document.body.classList.add('no-scroll'); // Lock scroll
            });
        }

        if (closeBtn && settingsModal) {
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

        // Init
        loadSettings();
    }

    // Initialize Settings
    initSettings();

    // Check if we need to reopen settings modal (after theme reload)
    if (sessionStorage.getItem('settingsModalOpen') === 'true') {
        const settingsModal = document.getElementById('settings-modal');
        if (settingsModal) {
            settingsModal.classList.add('active');
            document.body.classList.add('no-scroll'); // Re-lock scroll
        }
        sessionStorage.removeItem('settingsModalOpen');
    }

    // Accordion Animation Logic
    const accordions = document.querySelectorAll('.search-accordion');
    accordions.forEach(el => {
        const summary = el.querySelector('summary');
        const content = el.querySelector('.tag-cloud'); // Use strict content selector if possible, or calculate height
        // Since content layout varies, we animate the 'details' height itself.

        if (!summary) return;

        summary.addEventListener('click', (e) => {
            e.preventDefault(); // Prevent default toggle

            if (el.classList.contains('animating')) return;

            if (el.open) {
                // Closing
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

});
