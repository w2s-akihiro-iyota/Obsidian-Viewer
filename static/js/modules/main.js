// ==============================================
// main.js - Orchestrates module initialization
// ==============================================

document.addEventListener('DOMContentLoaded', async () => {
    // Load messages first
    await loadMessages();

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

    // Expose for usage in settings
    window.updateMermaidConfig = updateMermaidConfig;

    // Initialize mermaid after page load
    initMermaid();

    // Add copy buttons to all tables
    initTableCopy();

    // --- Page menu (three-dot menu) functionality ---
    const pageMenuBtn = document.getElementById('page-menu-btn');
    const pageMenuDropdown = document.getElementById('page-menu-dropdown');
    const exportPdfBtn = document.getElementById('export-pdf-btn');

    if (pageMenuBtn && pageMenuDropdown) {
        // Toggle dropdown
        pageMenuBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            pageMenuDropdown.classList.toggle('show');
        });
    }

    // PDF export functionality
    if (exportPdfBtn) {
        exportPdfBtn.addEventListener('click', () => {
            window.print();
        });
    }

    // --- Copy URL functionality ---
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
                try {
                    await copyToClipboard(url);
                    showToast(MESSAGES.system?.S002 || "URLをコピーしました", "success");
                } catch (fallbackErr) {
                    console.error('Final fallback copy failed:', fallbackErr);
                    showToast(MESSAGES.system?.S003 || "コピーに失敗しました", "error");
                }
            }
        });
    }

    // --- Scroll to Top Button ---
    const scrollToTopBtn = document.getElementById('scroll-to-top');

    if (scrollToTopBtn) {
        // Show/hide button based on scroll position
        window.addEventListener('scroll', () => {
            if (window.pageYOffset > SCROLL_SHOW_THRESHOLD) {
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

    // --- Add copy button to code blocks ---
    document.querySelectorAll('pre code').forEach((codeBlock) => {
        const pre = codeBlock.parentNode;
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'copy-button';
        button.textContent = 'Copy';

        pre.appendChild(button);

        button.addEventListener('click', () => {
            copyToClipboard(codeBlock.textContent).then(() => {
                button.textContent = 'Copied!';
                setTimeout(() => {
                    button.textContent = 'Copy';
                }, COPY_FEEDBACK_DURATION);
            });
        });
    });

    // --- Initialize Highlight.js ---
    if (window.hljs) {
        console.log('Highlight.js found, initializing...');
        hljs.highlightAll();

        // Fix: Promote .hljs class to <pre> to ensure background covers the whole block
        document.querySelectorAll('pre code.hljs').forEach(block => {
            if (block.parentElement && block.parentElement.tagName === 'PRE') {
                block.parentElement.classList.add('hljs');
            }
        });
        console.log('Highlight.js applied to blocks.');
    } else {
        console.error('Highlight.js not found! Check network or script tag.');
    }

    // Function to update Highlight.js theme (overrides the local one above with local file mapping)
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

    // --- Initialize modules ---
    initSearch();
    initSidebar();
    initHistory();
    initSettingsModule();
    initEditor();

    // --- Celebration check ---
    if (localStorage.getItem('showCelebration') === 'true') {
        localStorage.removeItem('showCelebration');
        setTimeout(() => showCelebration(), 300);
    }
});
