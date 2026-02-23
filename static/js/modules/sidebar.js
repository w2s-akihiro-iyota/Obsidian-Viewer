// ==============================================
// sidebar.js - Sidebar toggle, TOC, link preview, resize
// ==============================================

function initSidebar() {
    // --- Sidebar Toggle Logic ---
    const sidebar = document.getElementById('sidebar');
    const sidebarToggleBtns = document.querySelectorAll('.sidebar-toggle-btn');
    const sidebarOverlay = document.getElementById('sidebar-overlay');

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

            mobileToggleBtn.addEventListener('click', handleMobileClick);
            mobileToggleBtn.addEventListener('touchstart', handleMobileClick, { passive: false });
        }

        // Keep generic logic for desktop, but ensure mobile button doesn't double-fire
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

    // --- TOC Generator (Nested Tree for Outline) ---
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
        const stack = [{ level: 0, container: rootUl }];

        headers.forEach((header, index) => {
            // Add ID if missing for anchoring
            if (!header.id) {
                header.id = `toc-${index}`;
            }

            const level = parseInt(header.tagName.substring(1));
            const text = header.textContent;

            // Find the correct parent in the stack
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

    // --- Link Preview Logic ---
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

    // --- Sidebar Resize Logic ---
    initSidebarResize();
}

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
        if (newWidth < SIDEBAR_MIN_WIDTH) newWidth = SIDEBAR_MIN_WIDTH;
        if (newWidth > SIDEBAR_MAX_WIDTH) newWidth = SIDEBAR_MAX_WIDTH;

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
