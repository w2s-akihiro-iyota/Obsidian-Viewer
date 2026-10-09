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

    // 既存ノートの編集モード（/editor?path=... で開いたとき）
    const editPath = textarea.dataset.editPath || '';
    const dirtyBadge = document.getElementById('editor-dirty-badge');
    const conflictBar = document.getElementById('editor-conflict-bar');
    const backLink = document.querySelector('.editor-back-btn');
    let baseHash = '';   // 読み込んだ時点の中身のハッシュ。保存時の衝突検知に使う
    let isDirty = false;
    let isSaving = false;

    function setDirty(dirty) {
        isDirty = dirty;
        if (dirtyBadge) dirtyBadge.hidden = !dirty;
    }

    function showConflict(show) {
        if (conflictBar) conflictBar.hidden = !show;
    }

    // ノートを読み込み直す（初回表示・衝突時の「最新を読み込み直す」で使う）
    function loadNote() {
        return fetch(`/api/editor/note?path=${encodeURIComponent(editPath)}`)
            .then(async res => {
                const data = await res.json();
                if (!res.ok) throw new Error(data.message || 'ノートを読み込めませんでした');
                textarea.value = data.content;
                baseHash = data.hash;
                setDirty(false);
                showConflict(false);
                updatePreview();
            })
            .catch(err => {
                console.error('Load error:', err);
                showToast(err.message, 'error');
            });
    }

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
        if (editPath) setDirty(true);
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
            if (document.activeElement === textarea || filenameInput || editPath) {
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
        if (editPath) {
            updateNote(false);
            return;
        }
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

        // ローディング開始
        saveBtn.classList.add('loading');
        saveBtn.disabled = true;

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
            })
            .finally(() => {
                saveBtn.classList.remove('loading');
                saveBtn.disabled = false;
            });
    }

    // 既存ノートの上書き保存。force=true は衝突を承知で上書きする
    function updateNote(force) {
        // 保存中の二重送信（Ctrl+S の連打など）は、古い baseHash のまま飛んで偽の衝突になるので止める
        if (isSaving) return;
        if (!textarea.value.trim()) {
            showToast(MESSAGES.errors?.E203 || 'コンテンツが空です', 'error');
            textarea.focus();
            return;
        }

        isSaving = true;
        saveBtn.classList.add('loading');
        saveBtn.disabled = true;
        const sentContent = textarea.value;

        fetch('/api/editor/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: editPath, content: sentContent, base_hash: baseHash, force })
        })
            .then(async res => {
                const data = await res.json();
                if (res.ok) {
                    baseHash = data.hash;
                    // 応答を待つあいだに打った文字は、まだ保存されていない
                    setDirty(textarea.value !== sentContent);
                    showConflict(false);
                    if (backLink && data.slug) backLink.href = `/view/${data.slug}`;
                    showToast(data.message || 'ノートを更新しました', 'success');
                    if (data.host_saved === false) {
                        showToast('Vault に同じノートが無いため、ビューア側だけを更新しました', 'warning');
                    } else if (data.app_saved === false) {
                        showToast('Vault は更新しました。ビューアへの反映は次の同期で行われます', 'warning');
                    }
                } else if (res.status === 409) {
                    showConflict(true);
                    showToast(data.message, 'warning');
                } else {
                    showToast(data.message || '保存に失敗しました', 'error');
                }
            })
            .catch(err => {
                console.error('Update error:', err);
                showToast('保存に失敗しました', 'error');
            })
            .finally(() => {
                isSaving = false;
                saveBtn.classList.remove('loading');
                saveBtn.disabled = false;
            });
    }

    if (editPath) {
        document.getElementById('editor-conflict-overwrite')?.addEventListener('click', () => updateNote(true));
        document.getElementById('editor-conflict-reload')?.addEventListener('click', async () => {
            // 読み込み直すと入力内容が消えるため、先にクリップボードへ退避する
            try {
                await copyToClipboard(textarea.value);
                showToast('今の入力内容をクリップボードにコピーしました', 'info');
            } catch (err) {
                if (!confirm('入力内容をクリップボードにコピーできませんでした。破棄して読み込み直しますか？')) return;
            }
            loadNote();
        });

        // 保存していない変更があるまま離れようとしたら止める
        window.addEventListener('beforeunload', (e) => {
            if (!isDirty) return;
            e.preventDefault();
            e.returnValue = '';
        });

        loadNote();
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
