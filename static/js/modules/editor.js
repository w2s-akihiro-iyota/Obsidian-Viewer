// ==============================================
// editor.js - Markdown editor functionality
// ==============================================

function initEditor() {
    const textarea = document.getElementById('editor-textarea');
    const preview = document.getElementById('editor-preview');
    const saveBtn = document.getElementById('editor-save-btn');
    const filenameInput = document.getElementById('editor-filename');
    const resizer = document.getElementById('editor-resizer');

    if (!textarea || !preview) return; // エディタページでなければスキップ

    let previewTimer = null;
    const PREVIEW_DEBOUNCE = 500;

    // プレビュー後処理: highlight.js / KaTeX / Mermaid の再適用
    function postProcessPreview() {
        // Highlight.js
        if (window.hljs) {
            preview.querySelectorAll('pre code').forEach(block => {
                hljs.highlightElement(block);
            });
        }

        // KaTeX
        if (window.renderMathInElement) {
            renderMathInElement(preview, {
                delimiters: [
                    { left: '$$', right: '$$', display: true },
                    { left: '$', right: '$', display: false },
                    { left: '\\(', right: '\\)', display: false },
                    { left: '\\[', right: '\\]', display: true }
                ],
                throwOnError: false
            });
        }

        // Mermaid
        if (window.mermaid) {
            const mermaidBlocks = preview.querySelectorAll('pre code.language-mermaid');
            mermaidBlocks.forEach(block => {
                const pre = block.parentElement;
                const mermaidCode = block.textContent;
                const mermaidDiv = document.createElement('div');
                mermaidDiv.className = 'mermaid';
                mermaidDiv.textContent = mermaidCode;
                mermaidDiv.setAttribute('data-original-code', mermaidCode);
                pre.replaceWith(mermaidDiv);
            });

            const mermaidDivs = preview.querySelectorAll('.mermaid');
            if (mermaidDivs.length > 0) {
                window.mermaid.run({ nodes: mermaidDivs }).catch(err => console.error('Mermaid render error:', err));
            }
        }
    }

    // リアルタイムプレビュー
    function updatePreview() {
        const content = textarea.value;
        if (!content.trim()) {
            preview.innerHTML = '<p style="color:var(--text-muted);">プレビューするコンテンツがありません</p>';
            return;
        }

        fetch('/api/editor/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        })
            .then(res => res.text())
            .then(html => {
                preview.innerHTML = html;
                postProcessPreview();
            })
            .catch(err => {
                console.error('Preview error:', err);
                preview.innerHTML = '<p style="color:var(--text-muted);">プレビューの生成に失敗しました</p>';
            });
    }

    // デバウンス付き入力監視
    textarea.addEventListener('input', () => {
        clearTimeout(previewTimer);
        previewTimer = setTimeout(updatePreview, PREVIEW_DEBOUNCE);
    });

    // Tab キーで4スペース挿入
    textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Tab') {
            e.preventDefault();
            const start = textarea.selectionStart;
            const end = textarea.selectionEnd;
            const value = textarea.value;
            textarea.value = value.substring(0, start) + '    ' + value.substring(end);
            textarea.selectionStart = textarea.selectionEnd = start + 4;
            // 入力イベントを発火してプレビュー更新
            textarea.dispatchEvent(new Event('input'));
        }
    });

    // Ctrl+S で保存
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            // エディタページでのみ動作
            if (textarea && document.activeElement === textarea || filenameInput) {
                e.preventDefault();
                saveFile();
            }
        }
    });

    // 保存ボタン
    if (saveBtn) {
        saveBtn.addEventListener('click', () => saveFile());
    }

    function saveFile() {
        const filename = filenameInput ? filenameInput.value.trim() : '';
        const content = textarea.value;

        if (!filename) {
            showToast(MESSAGES.errors?.E201 || 'ファイル名を入力してください', 'error');
            if (filenameInput) filenameInput.focus();
            return;
        }

        if (!content.trim()) {
            showToast(MESSAGES.errors?.E203 || 'コンテンツが空です', 'error');
            textarea.focus();
            return;
        }

        fetch('/api/editor/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename, content })
        })
            .then(async res => {
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message || 'ファイルを保存しました', 'success');
                } else {
                    showToast(data.message || '保存に失敗しました', 'error');
                }
            })
            .catch(err => {
                console.error('Save error:', err);
                showToast('保存に失敗しました', 'error');
            });
    }

    // ペインリサイザー
    if (resizer) {
        let isResizing = false;
        const panes = document.querySelector('.editor-panes');
        const inputPane = document.querySelector('.editor-input-pane');
        const previewPane = document.querySelector('.editor-preview-pane');

        resizer.addEventListener('mousedown', (e) => {
            // モバイルでは無効
            if (window.matchMedia('(max-width: 768px)').matches) return;
            isResizing = true;
            document.body.classList.add('editor-resizing');
            resizer.classList.add('active');
            e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing || !panes) return;
            const rect = panes.getBoundingClientRect();
            const offset = e.clientX - rect.left;
            const totalWidth = rect.width;
            const ratio = Math.min(Math.max(offset / totalWidth, 0.2), 0.8);

            inputPane.style.flex = `0 0 ${ratio * 100}%`;
            previewPane.style.flex = `0 0 ${(1 - ratio) * 100}%`;
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                document.body.classList.remove('editor-resizing');
                resizer.classList.remove('active');
            }
        });
    }
}
