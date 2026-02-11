document.addEventListener('DOMContentLoaded', () => {
    // Theme toggle functionality
    const themeToggleBtn = document.getElementById('theme-toggle');

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

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);

            updateHighlightTheme(newTheme);

            // Reload page to reinitialize Mermaid with new theme
            setTimeout(() => location.reload(), 100);
        });
    }

    // Mermaid diagram rendering
    function initMermaid() {
        if (typeof window.mermaid === 'undefined') {
            // Mermaid not loaded yet, retry after a short delay
            setTimeout(initMermaid, 100);
            return;
        }

        const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
        const mermaidTheme = currentTheme === 'light' ? 'default' : 'dark';

        window.mermaid.initialize({
            startOnLoad: false,
            theme: mermaidTheme,
            securityLevel: 'loose'
        });

        // Find all mermaid code blocks
        const mermaidBlocks = document.querySelectorAll('pre code.language-mermaid');
        mermaidBlocks.forEach((block) => {
            const pre = block.parentElement;
            const mermaidCode = block.textContent;

            // Create a div for mermaid rendering
            const mermaidDiv = document.createElement('div');
            mermaidDiv.className = 'mermaid';
            mermaidDiv.textContent = mermaidCode;

            // Replace the pre element with the mermaid div
            pre.replaceWith(mermaidDiv);
        });

        // Render all mermaid diagrams
        if (mermaidBlocks.length > 0) {
            window.mermaid.run();
        }
    }

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
                <button class="copy-option" data-format="excel">Excel形式</button>
                <button class="copy-option" data-format="markdown">Markdown形式</button>
            `;

            copyContainer.appendChild(copyBtn);
            copyContainer.appendChild(dropdown);
            wrapper.insertBefore(copyContainer, table);

            // Toggle dropdown
            copyBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                dropdown.classList.toggle('show');
            });

            // Close dropdown when clicking outside
            document.addEventListener('click', () => {
                dropdown.classList.remove('show');
            });

            // Copy options
            dropdown.querySelectorAll('.copy-option').forEach((option) => {
                option.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const format = option.dataset.format;
                    copyTableToClipboard(table, format);
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

    function copyTableToClipboard(table, format) {
        let content = '';

        if (format === 'excel') {
            // TSV format for Excel
            const rows = table.querySelectorAll('tr');
            rows.forEach((row) => {
                const cells = row.querySelectorAll('th, td');
                const rowData = Array.from(cells).map(cell => cell.textContent.trim()).join('\t');
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

        // Copy to clipboard
        navigator.clipboard.writeText(content).then(() => {
            console.log('Table copied to clipboard in', format, 'format');
        }).catch(err => {
            console.error('Failed to copy table:', err);
        });
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
                searchResults.style.display = 'none';
                return;
            }

            debounceTimer = setTimeout(() => {
                fetch(`/api/search?q=${encodeURIComponent(query)}`)
                    .then(response => response.json())
                    .then(data => {
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
                    });
            }, 300); // 300ms debounce
        });

        // Hide results when clicking outside
        document.addEventListener('click', (e) => {
            if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
                searchResults.style.display = 'none';
            }
        });
    }

    // View toggle functionality (List/Grid)
    const listViewBtn = document.getElementById('list-view-btn');
    const gridViewBtn = document.getElementById('grid-view-btn');
    const fileList = document.querySelector('.file-list');

    console.log('View toggle elements:', { listViewBtn, gridViewBtn, fileList });

    if (listViewBtn && gridViewBtn && fileList) {
        // Load saved view preference from localStorage
        const savedView = localStorage.getItem('fileListView') || 'list';
        console.log('Saved view:', savedView);

        function setView(view) {
            console.log('Setting view to:', view);
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
            console.log('View set. File list classes:', fileList.className);
        }

        // Set initial view
        setView(savedView);

        // Button click handlers
        listViewBtn.addEventListener('click', () => {
            console.log('List view button clicked');
            setView('list');
        });
        gridViewBtn.addEventListener('click', () => {
            console.log('Grid view button clicked');
            setView('grid');
        });
    } else {
        console.error('View toggle elements not found!', { listViewBtn, gridViewBtn, fileList });
    }
});
