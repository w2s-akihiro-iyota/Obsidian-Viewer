// ==============================================
// mermaid.js - Mermaid diagram rendering
// ==============================================

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
