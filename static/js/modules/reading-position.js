// ==============================================
// reading-position.js - 前回読んでいた位置を覚えて「前回の続きから読む」で戻る（X-3）
// ==============================================
// 長いノートを開き直したとき、続きから読めるようにする。自動では戻さない
// （リンクから開いて先頭を読みたいときの邪魔をしない）。記録は localStorage の readingPositions

const READING_POSITIONS_KEY = 'readingPositions';
const READING_POSITIONS_MAX = 50;
const READING_SAVE_DELAY = 500;          // スクロールが止まってから保存するまで（ms）
const READING_RESUME_SHOW_MS = 8000;     // ボタンを出しておく時間
const READING_FAR_SCREENS = 1.5;         // これより下（画面の枚数）の位置だけを覚える
const READING_TOP_SCREENS = 0.5;         // これ未満なら「先頭付近にいる」
const READING_DISMISS_SCREENS = 0.25;    // 出したときの位置からこれ以上動いたら、自分で読み進めたとみなして消す
const READING_FADE_MS = 200;             // reading-position.css のフェード（--motion-base）より少し長く

function initReadingPosition() {
    // 記事ページだけ（ノートが見つからない画面 is-note-missing・一覧などでは動かさない）
    if (!document.body.classList.contains('page-view')) return;
    // 先読み（F-15）中は storage に触らない
    whenPageShown(() => {
        const path = window.location.pathname.slice('/view/'.length);
        showReadingResume(path);
        watchReadingPosition(path);
    });
}

function readReadingPositions() {
    try {
        const data = JSON.parse(localStorage.getItem(READING_POSITIONS_KEY) || '{}');
        return data && typeof data === 'object' && !Array.isArray(data) ? data : {};
    } catch (e) {
        return {};
    }
}

function writeReadingPositions(positions) {
    try {
        // 新しい順に最大件数だけ残す
        const kept = Object.entries(positions)
            .sort((a, b) => ((b[1] && b[1].at) || 0) - ((a[1] && a[1].at) || 0))
            .slice(0, READING_POSITIONS_MAX);
        localStorage.setItem(READING_POSITIONS_KEY, JSON.stringify(Object.fromEntries(kept)));
    } catch (e) {
        // 保存できなくても画面は動く
    }
}

// いまのスクロール位置を記録する。先頭付近なら、そのノートの記録を消す
function saveReadingPosition(path) {
    const positions = readReadingPositions();
    if (window.scrollY > window.innerHeight * READING_FAR_SCREENS) {
        positions[path] = { y: Math.round(window.scrollY), at: Date.now() };
    } else if (path in positions) {
        delete positions[path];
    } else {
        return;   // 書き換えるものが無ければ書かない
    }
    writeReadingPositions(positions);
}

function watchReadingPosition(path) {
    let timer = null;
    // このページで自分で読み進める（開いたときの位置から READING_DISMISS_SCREENS 以上動く）までは storage を書かない・消さない。
    // 開いた直後（「続きから」ボタンが出ている先頭付近）に離れたり、少し触っただけで離れたりしても、前回の位置を消さないため
    const startY = window.scrollY;
    let hasScrolled = false;
    const saveIfScrolled = () => { if (hasScrolled) saveReadingPosition(path); };
    window.addEventListener('scroll', () => {
        if (Math.abs(window.scrollY - startY) >= window.innerHeight * READING_DISMISS_SCREENS) hasScrolled = true;
        clearTimeout(timer);
        timer = setTimeout(saveIfScrolled, READING_SAVE_DELAY);
    }, { passive: true });
    window.addEventListener('pagehide', saveIfScrolled);
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') saveIfScrolled();
    });
}

function prefersReducedMotion() {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function showReadingResume(path) {
    const box = document.querySelector('.reading-resume');
    if (!box) return;
    const saved = readReadingPositions()[path];
    if (!saved || typeof saved.y !== 'number') return;

    const navType = performance.getEntriesByType('navigation')[0]?.type;
    const isFar = saved.y > window.innerHeight * READING_FAR_SCREENS;
    const isAtTop = window.scrollY < window.innerHeight * READING_TOP_SCREENS;
    if (!isFar || window.location.hash || navType === 'back_forward' || !isAtTop) return;

    const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
    const percent = maxScroll > 0 ? Math.min(100, Math.max(0, Math.round(saved.y / maxScroll * 100))) : 0;
    box.querySelector('.reading-resume-pct').textContent = `${percent}%`;

    const startY = window.scrollY;
    let hideTimer = null;
    function hide() {
        clearTimeout(hideTimer);
        window.removeEventListener('scroll', onScroll);
        box.classList.remove('is-visible');
        // フェードが終わってから外す（reduced-motion では CSS 側が即時なので待たない）
        setTimeout(() => { box.hidden = true; }, prefersReducedMotion() ? 0 : READING_FADE_MS);
    }
    function onScroll() {
        if (Math.abs(window.scrollY - startY) >= window.innerHeight * READING_DISMISS_SCREENS) hide();
    }

    box.querySelector('.reading-resume-go').addEventListener('click', () => {
        window.scrollTo({ top: saved.y, behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
        hide();
    });
    box.querySelector('.reading-resume-close').addEventListener('click', hide);

    box.hidden = false;
    requestAnimationFrame(() => box.classList.add('is-visible'));   // hidden を外した次の描画でフェードさせる
    window.addEventListener('scroll', onScroll, { passive: true });
    hideTimer = setTimeout(hide, READING_RESUME_SHOW_MS);
}
