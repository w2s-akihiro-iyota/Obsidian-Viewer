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

    // 名前入りで開いた新規作成（/editor?name=...）は、名前を決めてあるので本文から書き始める
    if (filenameInput && filenameInput.value) textarea.focus();

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
        // Mermaid（mermaid.js）: 色付けより先に図の div へ置き換える（Mermaid のコードに色を付けない）。
        // Mermaid 本体は図があるときだけ読み込み、読み込み中に何度呼ばれても 1 本しか読まない
        renderMermaidIn(preview);

        // Highlight.js
        if (window.hljs) {
            preview.querySelectorAll('pre code').forEach(block => {
                hljs.highlightElement(block);
            });
        }

        // KaTeX（math.js。記事ページと同じ描き方で、ドル記号の数式（.math.inline・.math.block）も描く。B-30）。
        // Mermaid の図（先に pre から div に置き換えている）の中の $ を数式にしない
        if (typeof renderMathIn === 'function') renderMathIn(preview, { ignoredClasses: ['mermaid'] });
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
            body: JSON.stringify({ content, path: editPath || "" })
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

    // Ctrl+S で保存。CapsLock 中は e.key が 'S' になるので、大文字も受ける。
    // Shift を押したとき（Ctrl+Shift+S）は、これまでどおりブラウザに任せる
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 's') {
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
    // マウスでもタッチ（769px 以上のタブレットなど）でもドラッグできるように pointer events で受ける（X-12）。
    // 押した指・ボタンを境目に捕まえ（setPointerCapture）、境目の外へ出ても動きと離したことが境目に届くようにする。
    // タッチでなぞってもページがスクロールしないのは、editor.css の .editor-resizer の touch-action: none。
    // キーボードでも動かせる（X-15）: 境目を選んで ← → で RESIZER_STEP ずつ、Home・End で端まで。
    // 今の入力欄の幅（%）は aria-valuenow に持ち、範囲（aria-valuemin・aria-valuemax）はドラッグとキーで同じ
    if (resizer) {
        const RESIZER_STEP = 5;     // ← → を 1 回押して動かす幅（%）
        let dragPointerId = null;   // ドラッグしている指・ボタンの pointerId（していなければ null）
        let grabOffset = 0;         // つかんだ所の、境目の左端からの距離（広げた範囲（X-14）でつかんでも、その所が境目についてくる）
        const panes = document.querySelector('.editor-panes');
        const inputPane = document.querySelector('.editor-input-pane');
        const phoneQuery = window.matchMedia('(max-width: 768px)');
        const ratioMin = Number(resizer.getAttribute('aria-valuemin'));
        const ratioMax = Number(resizer.getAttribute('aria-valuemax'));

        // 入力欄の幅（枠に対する %）を決める。CSS のカスタムプロパティで渡し、使うのは横並び（PC の幅）の CSS だけにする。
        // インラインの flex にすると、スマホの幅の縦並びにも残って入力欄が小さいままになる（X-10）。
        // プレビューは残りを使う（editor.css の .editor-pane の flex: 1）
        function setInputRatio(percent) {
            const ratio = Math.min(Math.max(percent, ratioMin), ratioMax);
            panes.style.setProperty('--editor-input-flex', `0 0 ${ratio}%`);
            resizer.setAttribute('aria-valuenow', String(Math.round(ratio)));
        }

        // スマホの幅（縦並び）では動かせないので、選べないようにし、読み上げからも外す
        function syncResizerForWidth() {
            resizer.tabIndex = phoneQuery.matches ? -1 : 0;
            if (phoneQuery.matches) resizer.setAttribute('aria-hidden', 'true');
            else resizer.removeAttribute('aria-hidden');
        }
        syncResizerForWidth();
        phoneQuery.addEventListener('change', syncResizerForWidth);
        if (panes && inputPane && !phoneQuery.matches) {
            const width = panes.getBoundingClientRect().width;
            if (width) resizer.setAttribute('aria-valuenow', String(Math.round(inputPane.getBoundingClientRect().width / width * 100)));
        }

        resizer.addEventListener('pointerdown', (e) => {
            // スマホの幅（縦並び）ではドラッグしない。ドラッグ中に別の指で触れても、最初の指のまま
            if (phoneQuery.matches || !panes || dragPointerId !== null) return;
            dragPointerId = e.pointerId;
            grabOffset = e.clientX - resizer.getBoundingClientRect().left;
            resizer.setPointerCapture(e.pointerId);
            // クリックで選び、続けて ← → で動かせるようにする（下の preventDefault で、ふつうのフォーカスが起きないため）
            resizer.focus({ preventScroll: true });
            document.body.classList.add('editor-resizing');
            resizer.classList.add('active');
            e.preventDefault();
        });

        resizer.addEventListener('pointermove', (e) => {
            if (e.pointerId !== dragPointerId) return;
            const rect = panes.getBoundingClientRect();
            setInputRatio((e.clientX - grabOffset - rect.left) / rect.width * 100);
        });

        resizer.addEventListener('keydown', (e) => {
            if (phoneQuery.matches || !panes || e.altKey || e.ctrlKey || e.metaKey) return;
            const now = Number(resizer.getAttribute('aria-valuenow'));
            const next = { ArrowLeft: now - RESIZER_STEP, ArrowRight: now + RESIZER_STEP, Home: ratioMin, End: ratioMax }[e.key];
            if (next === undefined) return;
            e.preventDefault();
            setInputRatio(next);
        });

        // 離したとき・ブラウザがドラッグを取り上げたとき（pointercancel）に終える。捕まえは離すとブラウザが外す
        const endDrag = (e) => {
            if (e.pointerId !== dragPointerId) return;
            dragPointerId = null;
            document.body.classList.remove('editor-resizing');
            resizer.classList.remove('active');
        };
        resizer.addEventListener('pointerup', endDrag);
        resizer.addEventListener('pointercancel', endDrag);
    }
}
