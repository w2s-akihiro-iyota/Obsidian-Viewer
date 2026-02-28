// ==============================================
// settings.js - Settings modal, help modal, welcome modal, tutorial, sync, directory browser
// ==============================================

function initSettingsModule() {
    // --- Help Modal Logic ---
    initHelpModal();

    // --- Welcome Modal Logic ---
    initWelcomeModal();

    // --- Settings Logic ---
    initSettings();

    // --- Sync Settings ---
    initSyncSettings();

    // --- Reopen settings modal after theme reload ---
    if (sessionStorage.getItem('settingsModalOpen') === 'true') {
        const settingsModal = document.getElementById('settings-modal');
        if (settingsModal) {
            settingsModal.classList.add('active');
            document.body.classList.add('no-scroll');
        }
        sessionStorage.removeItem('settingsModalOpen');
    }
}

// --- Help Modal Logic ---
function initHelpModal() {
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
                document.body.classList.add('no-scroll');
            });
        });

        const closeHelp = () => {
            helpModal.classList.remove('active');
            document.body.classList.remove('no-scroll');
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
}

// --- Welcome Modal Logic (localhost only, first visit) ---
function initWelcomeModal() {
    const welcomeModal = document.getElementById('welcome-modal');
    if (!welcomeModal) return;

    const closeWelcomeBtn = document.getElementById('close-welcome-modal');
    const welcomeStartBtn = document.getElementById('welcome-start-btn');

    // 初回判定: localStorageにフラグがなければ1秒後にポップアップ表示
    if (!localStorage.getItem('welcomeShown')) {
        setTimeout(() => {
            welcomeModal.classList.add('active');
            document.body.classList.add('no-scroll');
        }, 1000);
    }

    const closeWelcome = () => {
        welcomeModal.classList.add('closing');
        setTimeout(() => {
            welcomeModal.classList.remove('active', 'closing');
            document.body.classList.remove('no-scroll');
        }, 300);
        localStorage.setItem('welcomeShown', 'true');
    };

    if (closeWelcomeBtn) closeWelcomeBtn.addEventListener('click', closeWelcome);
    if (welcomeStartBtn) {
        welcomeStartBtn.addEventListener('click', () => {
            tutorialMode = true;
            tutorialStep = 0;
            closeWelcome();
            // 閉じアニメーション完了後に設定モーダルのファイル同期タブを開く
            setTimeout(() => {
                const settingsModal = document.getElementById('settings-modal');
                if (!settingsModal) return;
                settingsModal.classList.add('active');
                document.body.classList.add('no-scroll');
                // ファイル同期タブをアクティブにする
                const navItems = document.querySelectorAll('.settings-nav-item');
                const tabPanes = document.querySelectorAll('.settings-tab-pane');
                navItems.forEach(nav => nav.classList.toggle('active', nav.getAttribute('data-tab') === 'files'));
                tabPanes.forEach(pane => pane.classList.toggle('active', pane.id === 'settings-tab-files'));
                // チュートリアル開始
                setTimeout(() => startTutorial(), 100);
            }, 350);
        });
    }

    welcomeModal.addEventListener('click', (e) => {
        if (e.target === welcomeModal) closeWelcome();
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && welcomeModal.classList.contains('active')) {
            closeWelcome();
        }
    });
}

// --- Tutorial Logic ---
const TUTORIAL_STEPS = [
    {
        step: 1,
        title: 'ステップ 1: 同期を有効化',
        message: '「ファイル同期を有効にする」のトグルをONにしてください。',
        highlight: '.setting-custom-toggle'
    },
    {
        step: 2,
        title: 'ステップ 2: パスを入力して保存',
        message: 'コンテンツの元フォルダ、画像の元フォルダ、公開URLを入力し、「設定を保存」ボタンをクリックしてください。<br><span style="font-size:0.8em;color:var(--text-muted);">※ 画像フォルダと公開URLは任意です</span>',
        highlight: '#save-sync-settings-btn'
    },
    {
        step: 3,
        title: 'ステップ 3: 今すぐ同期',
        message: '「今すぐ同期」ボタンをクリックして、ファイルを同期しましょう。',
        highlight: '#manual-sync-btn'
    }
];

function startTutorial() {
    const banner = document.getElementById('tutorial-banner');
    if (!banner) return;
    banner.style.display = 'block';
    tutorialStep = 1;
    updateTutorialStep(1);

    const skipBtn = document.getElementById('tutorial-skip-btn');
    if (skipBtn) {
        skipBtn.onclick = () => endTutorial();
    }
}

function updateTutorialStep(step) {
    tutorialStep = step;
    const contentEl = document.getElementById('tutorial-step-content');
    const dots = document.querySelectorAll('.tutorial-dot');
    const connectors = document.querySelectorAll('.tutorial-connector');

    // インジケータ更新
    dots.forEach(dot => {
        const dotStep = parseInt(dot.dataset.step);
        dot.classList.remove('active', 'completed');
        if (dotStep < step) dot.classList.add('completed');
        else if (dotStep === step) dot.classList.add('active');
    });
    connectors.forEach((conn, i) => {
        conn.classList.toggle('completed', i < step - 1);
    });

    // ステップ内容更新
    const stepData = TUTORIAL_STEPS[step - 1];
    if (contentEl && stepData) {
        contentEl.innerHTML = `
            <div class="tutorial-step-title">${stepData.title}</div>
            <div class="tutorial-step-message">${stepData.message}</div>
        `;
    }

    // ハイライト更新
    document.querySelectorAll('.tutorial-highlight').forEach(el => el.classList.remove('tutorial-highlight'));
    if (stepData && stepData.highlight) {
        const target = document.querySelector(stepData.highlight);
        if (target) target.classList.add('tutorial-highlight');
    }
}

function advanceTutorial() {
    if (!tutorialMode) return;
    const nextStep = tutorialStep + 1;
    if (nextStep > TUTORIAL_STEPS.length) {
        endTutorial();
        // お祝いアニメーションはトップページ遷移後に表示（同期ハンドラ側で処理）
    } else {
        updateTutorialStep(nextStep);
    }
}

function endTutorial() {
    tutorialMode = false;
    tutorialStep = 0;
    const banner = document.getElementById('tutorial-banner');
    if (banner) banner.style.display = 'none';
    document.querySelectorAll('.tutorial-highlight').forEach(el => el.classList.remove('tutorial-highlight'));
}

// --- Settings Logic ---
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
    const codeThemeSelect = document.getElementById('setting-code-theme');
    const themeModeSelect = document.getElementById('setting-theme-select');
    const mermaidThemeSelect = document.getElementById('setting-mermaid-theme');
    const previewWidthRange = document.getElementById('setting-preview-width');
    const previewHeightRange = document.getElementById('setting-preview-height');
    const previewWidthLabel = document.getElementById('preview-width-value');
    const previewHeightLabel = document.getElementById('preview-height-value');
    const rebuildIndexBtn = document.getElementById('rebuild-index-btn');
    const clearCacheBtn = document.getElementById('clear-cache-btn');

    // State defaults
    const defaults = {
        fontSize: 'medium',
        readableWidth: true,
        lineNumbers: false,
        codeTheme: 'github-dark',
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
        const savedPreviewWidth = localStorage.getItem('previewWidth') || '400';
        const savedPreviewHeight = localStorage.getItem('previewHeight') || '300';

        // Apply to inputs
        if (fontSizeSelect) fontSizeSelect.value = savedFontSize;
        if (readableWidthCheck) readableWidthCheck.checked = isReadableWidth;
        if (lineNumbersCheck) lineNumbersCheck.checked = isLineNumbers;
        if (codeThemeSelect) codeThemeSelect.value = savedCodeTheme;
        if (themeModeSelect) themeModeSelect.value = currentTheme;
        if (mermaidThemeSelect) mermaidThemeSelect.value = savedMermaidTheme;
        if (previewWidthRange) {
            previewWidthRange.value = savedPreviewWidth;
            if (previewWidthLabel) previewWidthLabel.textContent = savedPreviewWidth + 'px';
        }
        if (previewHeightRange) {
            previewHeightRange.value = savedPreviewHeight;
            if (previewHeightLabel) previewHeightLabel.textContent = savedPreviewHeight + 'px';
        }

        // Apply to App
        applySettings({
            fontSize: savedFontSize,
            readableWidth: isReadableWidth,
            lineNumbers: isLineNumbers,
            codeTheme: savedCodeTheme,
            theme: currentTheme
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
            }
        });

        // Code Theme
        if (settings.codeTheme) {
            const codeThemes = ['github-dark', 'github', 'dracula', 'nord', 'tokyo-night-dark', 'atom-one-dark'];
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

        // Preview Tooltip Size
        const pw = localStorage.getItem('previewWidth') || '400';
        const ph = localStorage.getItem('previewHeight') || '300';
        document.documentElement.style.setProperty('--preview-width', pw + 'px');
        document.documentElement.style.setProperty('--preview-max-height', ph + 'px');
    };

    // Event Listeners (Moved inside initial check)
    if (settingsModal && openBtns.length > 0 && closeBtn) {
        openBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                settingsModal.classList.add('active');
                document.body.classList.add('no-scroll');
            });
        });

        closeBtn.addEventListener('click', () => {
            settingsModal.classList.remove('active');
            document.body.classList.remove('no-scroll');
            if (tutorialMode) endTutorial();
        });
    }

    if (settingsModal) {
        settingsModal.addEventListener('click', (e) => {
            if (e.target === settingsModal) {
                settingsModal.classList.remove('active');
                document.body.classList.remove('no-scroll');
                if (tutorialMode) endTutorial();
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
            const codeThemes = ['github-dark', 'github', 'dracula', 'nord', 'tokyo-night-dark', 'atom-one-dark'];
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
            const savedMermaidTheme = localStorage.getItem('mermaidTheme') || 'default';
            if (savedMermaidTheme === 'default') {
                if (typeof window.updateMermaidConfig === 'function') {
                    window.updateMermaidConfig();
                }
            }
        });
    }

    if (previewWidthRange) {
        previewWidthRange.addEventListener('input', (e) => {
            const val = e.target.value;
            localStorage.setItem('previewWidth', val);
            if (previewWidthLabel) previewWidthLabel.textContent = val + 'px';
            document.documentElement.style.setProperty('--preview-width', val + 'px');
        });
    }

    if (previewHeightRange) {
        previewHeightRange.addEventListener('input', (e) => {
            const val = e.target.value;
            localStorage.setItem('previewHeight', val);
            if (previewHeightLabel) previewHeightLabel.textContent = val + 'px';
            document.documentElement.style.setProperty('--preview-max-height', val + 'px');
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
                        rebuildIndexBtn.textContent = '再構築';
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
        if (enabledToggle.checked) {
            // 有効化: チュートリアル進行
            if (tutorialMode && tutorialStep === 1) {
                setTimeout(() => advanceTutorial(), 500);
            }
        } else {
            // 無効化: 確認の上で即座に保存
            if (!confirm("ファイル同期を無効にしますか？")) {
                enabledToggle.checked = true;
                toggleInputs(true);
                return;
            }
            disableSync();
        }
    });

    autoSyncToggle.addEventListener('change', () => {
        toggleAutoSyncInputs(autoSyncToggle.checked);
    });

    // Save Button Handler
    if (saveBtn) {
        saveBtn.addEventListener('click', () => {
            if (tutorialMode && tutorialStep === 2) {
                saveConfig();
                return;
            }
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
            el.classList.remove('warning');
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
                    if (tutorialMode && tutorialStep === 2) {
                        setTimeout(() => advanceTutorial(), 600);
                    }
                    if (data.warnings) {
                        Object.keys(data.warnings).forEach(key => {
                            const errorEl = document.getElementById(`${key}-error`);
                            if (errorEl) {
                                errorEl.textContent = data.warnings[key];
                                errorEl.style.display = 'block';
                                errorEl.classList.add('warning');
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

    // 同期を無効化して全設定を初期化
    function disableSync() {
        const config = {
            sync_enabled: false,
            auto_sync_enabled: false,
            content_src: "",
            images_src: "",
            base_url: "",
            interval_minutes: 60,
            last_sync: ""
        };

        fetch('/api/sync/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        })
            .then(async res => {
                if (res.ok) {
                    // UI側の入力値も初期化
                    autoSyncToggle.checked = false;
                    contentSrcInput.value = '';
                    imagesSrcInput.value = '';
                    if (baseUrlInput) baseUrlInput.value = '';
                    intervalSelect.value = 60;
                    lastSyncLabel.textContent = '';
                    toggleAutoSyncInputs(false);
                    clearErrors();
                    showToast("ファイル同期を無効にしました", "success");
                } else {
                    throw new Error("Save failed");
                }
            })
            .catch(err => {
                console.error("Failed to disable sync", err);
                showToast("設定の保存に失敗しました", "error");
                // 保存失敗時はトグルを元に戻す
                enabledToggle.checked = true;
                toggleInputs(true);
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

    // Manual Sync Logic
    manualSyncBtn.addEventListener('click', () => {
        if (!(tutorialMode && tutorialStep === 3)) {
            if (!confirm("ファイルと画像の同期を今すぐ実行しますか？")) return;
        }

        manualSyncBtn.classList.add('loading');
        manualSyncBtn.disabled = true;

        fetch('/api/sync', { method: 'POST' })
            .then(async res => {
                const data = await res.json();
                if (res.ok) {
                    if (tutorialMode && tutorialStep === 3) {
                        endTutorial();
                        // チュートリアル完了時のみお祝いアニメーションを表示
                        localStorage.setItem('showCelebration', 'true');
                    }
                    window.location.href = '/';
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
