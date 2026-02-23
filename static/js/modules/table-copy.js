// ==============================================
// table-copy.js - Table copy-to-clipboard functionality
// ==============================================

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
        await copyToClipboard(content);
    } catch (err) {
        console.error('Copy failed:', err);
        alert('Copy failed. Please try manually.');
    }
}

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
                }, COPY_FEEDBACK_DURATION);
            });
        });
    });
}

function initTableCopy() {
    addTableCopyButtons();
}
