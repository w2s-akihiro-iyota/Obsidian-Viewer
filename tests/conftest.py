"""テスト全体の共通設定

E2E のテストファイル（test_e2e_*.py）は、2 ファイル以上で使う物（E2E_* の定数・import_playwright）を
`from conftest import ...` で読む（pytest の既定の読み込み方では、pytest が読んだこの conftest と同じモジュールになる）
"""
import asyncio
import base64
import re
import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit

import pytest

from app import cache
from app.api import content as content_api
from app.api import editor as editor_api
from app.api import media as media_api
from app.core import indexing, sync_history
from app.services import note_editing, wikilinks
from app.utils import helpers


@pytest.fixture(autouse=True)
def _isolate_sync_history(tmp_path, monkeypatch):
    """同期の記録（F-7）を tmp_path に書かせる（本物の app/sync_history.json に混ぜない）"""
    monkeypatch.setattr(sync_history, "SYNC_HISTORY_FILE", tmp_path / "sync_history.json")


def cache_names() -> list[str]:
    """app/cache.py のキャッシュの名前（大文字の変数）。名前を書き並べないので、キャッシュを足してもここは直さない"""
    return [name for name in vars(cache) if name.isupper()]


@pytest.fixture
def isolated_caches(monkeypatch):
    """
    app/cache.py のキャッシュを、テストが終わったら元の値に戻す（Q-25）

    索引を作り直すテスト（refresh_global_caches）は、この fixture を使う。作り直しで差し替えたキャッシュを、ほかのテストに残さない。
    """
    for name in cache_names():
        monkeypatch.setattr(cache, name, getattr(cache, name))


@pytest.fixture
def use_test_vault(monkeypatch):
    """
    アプリがノートと添付を読む場所を、テスト用のフォルダに差し替える関数（テストが終われば元に戻る）

    読む側（表示・索引・リンク・編集・添付の配信）の CONTENT_DIR・MEDIA_DIR の差し替えは、ここにだけ書く。
    テスト用のノートを置く fixture（test_api.py の site・E2E の e2e_vault など）は、これを通す。
    同期（app/services/sync.py）と添付の引っ越し（media_migration.py）の CONTENT_DIR・MEDIA_DIR は書き込み先で、
    目的が違うので、それぞれのテストが自分で差し替える。
    使い方: use_test_vault(ノートのフォルダ, 添付のフォルダ)。添付のフォルダは無くてもよい（本物の media/ を読まないための置き場）
    """
    def use(notes_dir, media_dir):
        for module in (content_api, editor_api, indexing, note_editing, wikilinks):
            monkeypatch.setattr(module, "CONTENT_DIR", notes_dir)
        monkeypatch.setattr(indexing, "MEDIA_DIR", media_dir)
        monkeypatch.setattr(media_api, "MEDIA_DIR", media_dir)
    return use


# ==============================================
# ノートに書いた生の HTML（S-10）。描画の契約（test_html_sanitizer.py）と API の契約（test_api.py）で使う
# ==============================================

# 動いたら・要素や属性として残ったら、この印が出力に残る書き方にしてある（文字として残ることも無い）
RAW_HTML_MARK = "s10xss"
RAW_HTML_ATTACKS = (
    f"<script>{RAW_HTML_MARK}()</script>\n\n"
    f'<img src="x" onerror="{RAW_HTML_MARK}()">\n\n'
    f'<a href="javascript:{RAW_HTML_MARK}()">リンク</a>\n\n'
    f'<iframe src="javascript:{RAW_HTML_MARK}()"></iframe>\n\n'
    '<div hx-get="/api/sync/run" hx-trigger="load">s10</div>\n\n'
    f'<svg onload="{RAW_HTML_MARK}()"><script>{RAW_HTML_MARK}()</script></svg>\n'
)
RAW_HTML_NOTE = "危ない.md"            # 本文に RAW_HTML_ATTACKS を書いた公開ノート
RAW_HTML_EMBEDDING_NOTE = "埋め込む.md"  # RAW_HTML_NOTE を埋め込む公開ノート
RAW_HTML_PARTNER_NOTE = "相手.md"      # リンク・埋め込み・Dataview の相手（見出し・節・タグ・true/false の項目）


@pytest.fixture
def raw_html_site(tmp_path, use_test_vault, isolated_caches):
    """生の HTML を書いたノート・それを埋め込むノート・アプリの記法の相手のノート・非公開のノートを置いた Vault（索引を作り直す）"""
    vault, media = tmp_path / "vault", tmp_path / "media"
    vault.mkdir()
    media.mkdir()
    use_test_vault(vault, media)
    (media / "pic.png").write_bytes(b"png")
    notes = {
        RAW_HTML_PARTNER_NOTE: ("---\npublish: true\ntags: [t1]\ndone: true\nflag: false\n---\n"
                                "# 相手の見出し\n相手の本文 #相手タグ\n\n## 節\n節の本文\n"),
        RAW_HTML_NOTE: f"---\npublish: true\n---\n本文\n\n{RAW_HTML_ATTACKS}",
        RAW_HTML_EMBEDDING_NOTE: f"---\npublish: true\n---\n前\n\n![[{RAW_HTML_NOTE[:-3]}]]\n",
        "非公開.md": "---\npublish: false\n---\n非公開の本文\n",
    }
    for rel, text in notes.items():
        (vault / rel).write_text(text, encoding="utf-8")
    indexing.refresh_global_caches()
    return vault


# ==============================================
# E2E（ブラウザで JS の動きを確かめる。Q-17）
#
# テスト用のノートだけを読むサーバーを、空いているポートにスレッドで立て、Playwright の Chromium で開く。
# 本物のサーバー（8000・8002 番）と content（実データ）には触らない。
# Playwright か Chromium が入っていない環境では、理由と入れ方を付けて skip する（CLAUDE.md の Testing）
# ==============================================

E2E_INSTALL_HINT = ("入れ方: apt-get update && apt-get install -y libatomic1 → pip install playwright==1.65.2 → "
                    "python -m playwright install --with-deps --only-shell chromium（CLAUDE.md の Testing）")
# 画面の幅（E2ESite.open・resize の width）。PC と、768px 以下のスマホ
E2E_PC = "PC"
E2E_PHONE = "スマホ"
E2E_VIEWPORTS = {
    E2E_PC: {"width": 1280, "height": 900},
    E2E_PHONE: {"width": 390, "height": 844},
}
# 閲覧者の種類（E2ESite.open の viewer）。管理者は管理用ポート、外部の人は公開用ポートのサーバーで開く
E2E_ADMIN = "管理者"
E2E_PUBLIC = "外部の人"
E2E_VIEWERS = (E2E_ADMIN, E2E_PUBLIC)
# 2 つ以上のテストファイルで使うセレクタ（1 ファイルだけで使うものは、そのファイルに置く）
E2E_GRAPH_PANEL = "#local-graph"            # つながりのパネル（768px 以下では下からのシート）
E2E_GRAPH_BUTTON = "#local-graph-toggle"    # つながりのボタン（768px 以下では「＋」の中の最初の項目）
E2E_SHORTCUT_SHEET = "#shortcut-sheet"      # ? のショートカット一覧
E2E_DIR_BROWSER = "#dir-browser-modal"      # 設定の中のフォルダ選び（E2ESite.open_dir_browser で開く）
E2E_ACTIVE = re.compile(r"\bactive\b")      # モーダル・ドロワーが開いている印のクラス
# フォルダ選び（E2ESite.open_dir_browser）で返す偽の同期の設定（本物の設定は読まない）。同期を有効にしておくと「参照...」が出る
E2E_FAKE_SYNC_CONFIG = {"sync_enabled": True, "auto_sync_enabled": False, "content_src": "/e2e-元", "extra_sources": [],
                        "images_src": "", "base_url": "", "interval_minutes": 60, "last_sync": ""}
# サーバーが立ち上がるまで・止まるまで待つ上限（秒）
E2E_SERVER_START_TIMEOUT = 15
E2E_SERVER_STOP_TIMEOUT = 10
# expect と E2ESite.wait_until があきらめるまでの時間（ms）。ふつうは Playwright の expect の既定と同じ 5 秒。
# xfail の印が付いたテスト（直っていない不具合）は、判定が待ちを使い切って落ちるので 2 秒にして全件の時間を抑える
E2E_WAIT_MS = 5000
E2E_XFAIL_WAIT_MS = 2000
# ブラウザから送ってよいリクエスト。GET・HEAD のほかは、書き込まない POST（エディタのプレビュー。Markdown を描いて返すだけ）だけ
E2E_SAFE_METHODS = {"GET", "HEAD"}
E2E_READ_ONLY_POSTS = {"/api/editor/preview"}
# CSP の違反（securitypolicyviolation）を拾う仕掛け（S-10）。open_path が開くどのページにも入れる。
# 今のページの分は window.__e2eCspViolations に、開いたページ全部の分は console を通して E2ESite.csp_violations にためる
# （console の知らせは、そのあとに呼んだ page.evaluate などの戻りより先に届く）
_E2E_CSP_MARK = "[e2e-csp]"
_E2E_CSP_LISTENER = """
window.__e2eCspViolations = [];
window.addEventListener('securitypolicyviolation', (event) => {
    const text = [decodeURIComponent(location.pathname), event.effectiveDirective, event.blockedURI,
                  `${event.sourceFile}:${event.lineNumber}`, event.sample].join(' ');
    window.__e2eCspViolations.push(text);
    console.info(MARK + ' ' + text);
}, true);
""".replace("MARK", repr(_E2E_CSP_MARK))

# テスト用のノート（E2E_NOTES）のうち、テストが名前で使うもの
E2E_ENTRY_NOTE = "入口のノート.md"   # つながり 2 歩・見出し・長い本文。たいていのテストはここを開く
E2E_IMAGE_NOTE = "画像のノート.md"   # 先頭に画像（押すと拡大）と長い本文
E2E_RICH_NOTE = "描画のノート.md"    # 数式・Mermaid・コード・カードリンク・画像（CSP の下でも描けるか。S-10）
E2E_RAW_HTML_NOTE = "生のHTMLのノート.md"   # 本文に生の <script>・onerror・javascript: のリンク（動かないか。S-10）
E2E_SEARCH_WORD = "ipsum"           # 非公開のノート以外の本文にある語（クイックスイッチャーで候補が 3 件以上出る）
# 描画のノートの Mermaid の点を押したときに呼ばせようとする関数の名前（securityLevel が loose なら呼ばれる。S-10）
E2E_MERMAID_CALLBACK = "e2eMermaidCallback"

# テスト用の添付（添付の置き場からのパス → 中身）。1×1 の PNG を、ノートの ![[...|幅x高さ]] で押せる大きさに広げて出す
E2E_IMAGE = "e2e-画像.png"
E2E_MEDIA = {
    E2E_IMAGE: base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="),
}

# 本文の段落（記事ページがスクロールできる長さにする）
_E2E_LONG_BODY = "\n\n".join(f"段落 {i}: 長い本文。スクロールできる長さにするための文。" for i in range(40))

# テスト用のノート（ビューアのパス → 中身）
# - 入口: つながりが 2 歩（入口 → 先A・先B、先B → 二歩先）。見出し（h1〜h3）と長い本文
# - フォルダ 2 段（フォルダ1/サブ/）に 3 件（ツリーの矢印キー用）
# - ひとり: どこともつながらない。非公開: 外部の人には見えない
# - 画像: 先頭の画像（E2E_IMAGE）を押すと拡大する。本文が長く、裏の本文がスクロールできる
# - 描画: 数式（インラインとブロック）・Mermaid（ラベルの <br/> と、点を押すと関数を呼ぶ click）・コード・カードリンク・画像。
#   カードリンクの画像は https の外の画像（CSP の img-src https:）。どこにもつながらない 127.0.0.1:1 にして、外へは出ない
# - 生の HTML: 動いたら window に印を付ける <script>・onerror・javascript: のリンク。サニタイズと CSP のどちらかで止まる
E2E_NOTES = {
    E2E_ENTRY_NOTE: ("---\npublish: true\n---\n# 入口の見出し\n\n[[つながり先のノートA]] と [[つながり先のノートB]] へ。\n\n"
                     f"## 中くらいの見出し\n\n{_E2E_LONG_BODY}\n\n### 小さい見出し\n\nおわり {E2E_SEARCH_WORD}\n"),
    "フォルダ1/つながり先のノートA.md": f"---\npublish: true\n---\n# 先A\n\n先A の本文 {E2E_SEARCH_WORD}\n",
    "フォルダ1/サブ/つながり先のノートB.md": f"---\npublish: true\n---\n# 先B\n\n先B の本文 {E2E_SEARCH_WORD}。[[二歩先のノート]] へ\n",
    "フォルダ1/サブ/二歩先のノート.md": f"---\npublish: true\n---\n# 二歩先\n\n二歩先の本文 {E2E_SEARCH_WORD}\n",
    "ひとりのノート.md": f"---\npublish: true\n---\n# ひとり\n\nどこともつながらない {E2E_SEARCH_WORD}\n",
    "非公開のノート.md": "---\npublish: false\n---\n# 非公開\n\n非公開の本文\n",
    E2E_IMAGE_NOTE: f"---\npublish: true\n---\n# 画像\n\n![[{E2E_IMAGE}|320x160]]\n\n{_E2E_LONG_BODY}\n",
    E2E_RICH_NOTE: ("---\npublish: true\n---\n# 描画\n\n数式 $E=mc^2$ と\n\n$$\n\\int_0^1 x\\,dx\n$$\n\n"
                    "```python\nprint(\"色付け\")\n```\n\n"
                    "```mermaid\nflowchart LR\n    A[\"一行目<br/>二行目\"] --> B[\"押せる点\"]\n"
                    f"    click B {E2E_MERMAID_CALLBACK}\n```\n\n"
                    "```cardlink\nurl: https://127.0.0.1:1/e2e-card\ntitle: カードリンク\n"
                    "image: https://127.0.0.1:1/e2e-card.png\n```\n\n"
                    f"![[{E2E_IMAGE}|320x160]]\n"),
    E2E_RAW_HTML_NOTE: ("---\npublish: true\n---\n# 生のHTML\n\n<script>window.__e2eNoteScript = 1</script>\n\n"
                        '<img src="/static/images/e2e-missing.png" onerror="window.__e2eNoteOnerror = 1">\n\n'
                        '<a href="javascript:window.__e2eNoteLink = 1">動いてはいけないリンク</a>\n'),
}


def import_playwright():
    """
    playwright.sync_api を読み込んで返す（E2E のテストファイルの先頭と e2e_browser が使う）

    skip するのは「入っていない」ことが確かなとき（playwright のモジュール自体が無い）だけ。
    入っているのに読み込めない（greenlet が無いなどの壊れた導入）は失敗にする。skip にすると、E2E が丸ごと飛んでいるのに
    「全件通った」に見えるため
    """
    try:
        import playwright.sync_api as api
    except ImportError as error:
        if isinstance(error, ModuleNotFoundError) and error.name == "playwright":
            pytest.skip(f"Playwright が入っていないので E2E を飛ばす。{E2E_INSTALL_HINT}", allow_module_level=True)
        pytest.fail(f"Playwright を読み込めない（{error}）。{E2E_INSTALL_HINT}", pytrace=False)
    return api


def _first_line(error: Exception) -> str:
    return (str(error).strip().splitlines() or [type(error).__name__])[0]


@dataclass(frozen=True)
class E2EServers:
    """E2E のテスト用サーバーのポート（どちらも 127.0.0.1 の空きポート）"""
    admin_port: int
    public_port: int


@pytest.fixture(scope="module")
def e2e_browser():
    """
    E2E のブラウザ（Chromium の headless shell を 1 つ。E2E のテストファイルの中で使い回す）

    ファイルごとに起動し、ファイルが終わったら止める（テスト全体で使い回さない）。Playwright の同期 API は、動いているあいだ
    このスレッドのイベントループを「走っている」ことにしたままにするので、あとに続く asyncio.run を使うテスト（test_sync.py など）が
    「asyncio.run() cannot be called from a running event loop」で落ちる。止めれば元に戻る。
    Chromium が入っていない（"Executable doesn't exist"）ときだけ skip し、ほかの起動の失敗（共有ライブラリが足りない等）は
    失敗にする（import_playwright と同じく、壊れた環境を「全件通った」に見せない）
    """
    api = import_playwright()
    try:
        playwright = api.sync_playwright().start()
    except Exception as error:      # Playwright の driver（同梱の Node）が動かない。libatomic1 が無いときなど
        pytest.fail(f"Playwright を起動できない（{_first_line(error)}）。{E2E_INSTALL_HINT}", pytrace=False)
    try:
        browser = playwright.chromium.launch()
    except api.Error as error:
        playwright.stop()
        if "Executable doesn't exist" in str(error):
            pytest.skip(f"Chromium が入っていないので E2E を飛ばす（{_first_line(error)}）。{E2E_INSTALL_HINT}")
        pytest.fail(f"Chromium を起動できない（{_first_line(error)}）。{E2E_INSTALL_HINT}", pytrace=False)
    yield browser
    browser.close()
    playwright.stop()


@pytest.fixture(scope="session")
def e2e_servers():
    """
    管理用と公開用の 2 つのサーバー（app/server.py と同じく 1 つのイベントループで 2 つ待ち受ける。テスト全体で使い回す）

    ポートは 127.0.0.1 の空きポート（本物の 8000・8002 番とは別）。lifespan は切る（起動時の同期・索引作りを走らせない。
    読むノートは各テストが e2e_vault で差し替え、索引もそこで作る）。
    管理者とみなすポート（ADMIN_PORT）の差し替えは、テストのあいだだけ e2e がする
    """
    import uvicorn

    from app.main import app

    sockets = []
    for _ in range(2):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sockets.append(sock)
    servers = [uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="warning")) for _ in sockets]

    async def serve_all():
        await asyncio.gather(*(server.serve(sockets=[sock]) for server, sock in zip(servers, sockets)))

    thread = threading.Thread(target=lambda: asyncio.run(serve_all()), name="e2e-servers", daemon=True)
    thread.start()
    deadline = time.monotonic() + E2E_SERVER_START_TIMEOUT
    while not all(server.started for server in servers):
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("E2E のテスト用サーバーが起動しなかった")
        time.sleep(0.05)

    admin_sock, public_sock = sockets
    yield E2EServers(admin_port=admin_sock.getsockname()[1], public_port=public_sock.getsockname()[1])

    for server in servers:
        server.should_exit = True
    thread.join(E2E_SERVER_STOP_TIMEOUT)
    for sock in sockets:
        sock.close()


@pytest.fixture
def e2e_vault(tmp_path, use_test_vault, isolated_caches):
    """E2E のテスト用のノート（E2E_NOTES）と添付（E2E_MEDIA）を置き、アプリの読む場所を差し替えて索引を作る"""
    notes_dir = tmp_path / "vault"
    for rel, text in E2E_NOTES.items():
        path = notes_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    media_dir = tmp_path / "media"
    for rel, data in E2E_MEDIA.items():
        path = media_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    use_test_vault(notes_dir, media_dir)
    indexing.refresh_global_caches()
    return notes_dir


@dataclass
class E2ESite:
    """
    E2E のテストから使う、テスト用のノートだけのサイト（ページを開く・準備ができるまで待つ）

    開いたページの JS のエラー（pageerror）は errors に、止めた書き込み（_block_writes）は blocked に、
    CSP の違反（_E2E_CSP_LISTENER）は csp_violations に集め、テストの終わりにどれも 0 件であることを e2e が確かめる
    """
    browser: object
    servers: E2EServers
    wait_ms: int = E2E_WAIT_MS      # expect で書けない待ち（wait_until・応答など）の上限。xfail のテストでは短くする（e2e）
    errors: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    csp_violations: list[str] = field(default_factory=list)
    contexts: list = field(default_factory=list)

    ENTRY = E2E_ENTRY_NOTE
    SEARCH_WORD = E2E_SEARCH_WORD

    def open(self, note: str = ENTRY, *, viewer: str = E2E_ADMIN, width: str = E2E_PC, welcome: bool = False):
        """ノートの記事ページを開く（URL はファイル名ではなくスラッグ）。引数は open_path と同じ"""
        return self.open_path(f"/view/{quote(cache.PATH_TO_SLUG[note])}", viewer=viewer, width=width, welcome=welcome)

    def open_path(self, path: str, *, viewer: str = E2E_ADMIN, width: str = E2E_PC, welcome: bool = False):
        """
        画面（/editor など）を新しいブラウザ（context）で開き、キー操作を受け付けるまで待ったページを返す

        - viewer: E2E_ADMIN（管理用ポート）か E2E_PUBLIC（公開用ポート）
        - width: E2E_PC（1280×900）か E2E_PHONE（390×844）
        - welcome: ようこそ（管理者の初回だけ、画面に出た 1 秒後に出て G・? を止める）を出すか。既定は出さない
          （True でも、出るのを待たずに返す。出たかはテストが expect で待つ）
        - PC のサイドバーは開いておく（既定は畳む）
        - GET・HEAD 以外のリクエストは、既定で止める（_block_writes）
        - CSP の違反を拾う（_E2E_CSP_LISTENER）
        """
        port = {E2E_ADMIN: self.servers.admin_port, E2E_PUBLIC: self.servers.public_port}[viewer]
        context = self.browser.new_context(viewport=E2E_VIEWPORTS[width])
        self.contexts.append(context)
        context.route("**/*", self._block_writes)
        context.add_init_script(_E2E_CSP_LISTENER)
        init_script = "localStorage.setItem('sidebarCollapsed', 'false');"
        if not welcome:
            init_script += " localStorage.setItem('welcomeShown', 'true');"
        context.add_init_script(init_script)
        page = context.new_page()
        page.on("pageerror", lambda error: self.errors.append(f"{page.url}: {error}"))
        page.on("console", self._collect_csp_violation)
        page.goto(f"http://127.0.0.1:{port}{path}")
        self.wait_ready(page)
        return page

    def _collect_csp_violation(self, message) -> None:
        """_E2E_CSP_LISTENER が console に出した CSP の違反をためる"""
        if message.text.startswith(_E2E_CSP_MARK):
            self.csp_violations.append(message.text[len(_E2E_CSP_MARK):].strip())

    def take_csp_violations(self) -> list[str]:
        """ためた CSP の違反を返して空にする（わざと違反させるテストが、終わりの確かめ（e2e）に残さないために使う）"""
        taken = list(self.csp_violations)
        self.csp_violations.clear()
        return taken

    def _block_writes(self, route) -> None:
        """
        ブラウザからの書き込み（GET・HEAD 以外。書き込まないプレビューの POST は除く）を、サーバーに届く前に止めて記録する

        テスト用のサーバーは、ノートの置き場こそテスト用に差し替えているが、設定は本物の app/server_config.yaml を読む
        （Vault の場所・同期の設定）。テストが間違って書き込み（エディタの保存・設定の保存・同期など）を送ると、
        本物の Vault や設定に書きに行く恐れがあるので、context の既定で止める。
        書き込みを確かめたいテストは page.route で受けて偽の応答を返す（page の route が context の route より先に効くので、
        受けたリクエストはここへ来ない）
        """
        request = route.request
        path = urlsplit(request.url).path
        if request.method in E2E_SAFE_METHODS or (request.method == "POST" and path in E2E_READ_ONLY_POSTS):
            route.fallback()
            return
        self.blocked.append(f"{request.method} {path}")
        route.abort()

    @staticmethod
    def resize(page, width: str) -> None:
        """開いたページの幅を変える（width は open と同じ E2E_PC か E2E_PHONE）"""
        page.set_viewport_size(E2E_VIEWPORTS[width])

    @staticmethod
    def wait_ready(page) -> None:
        """
        キー操作を受け付けるまで待つ（ページを移ったあとにも使う。固定の時間は待たない）

        検索・?・ヘルプの keydown が付くのは、/api/messages の応答を読み終えたあと（main.js の await loadMessages()）。
        応答を MESSAGES に入れたあとの初期化は、ほかの処理をはさまずに続けて走るので、MESSAGES が埋まっていれば keydown も付いている
        """
        page.wait_for_function("() => Object.keys(MESSAGES.system).length > 0")

    def open_dir_browser(self, page, **list_dirs) -> None:
        """
        管理者のページで設定を開き、同期の元フォルダの「参照...」からフォルダ選び（E2E_DIR_BROWSER）を開く（開いたかはテストが確かめる）

        同期の設定（/api/sync/config）は E2E_FAKE_SYNC_CONFIG、フォルダの一覧（/api/list-dirs）は list_dirs
        （route.fulfill の引数。json・status など）の偽の応答にする。本物の設定と、コンテナのフォルダは読まない。
        同期の設定はページを読んだときに読むので、偽の応答を付けてから読み直す
        """
        page.route(re.compile(r"/api/sync/config$"), lambda route: route.fulfill(json=E2E_FAKE_SYNC_CONFIG))
        page.route(re.compile(r"/api/list-dirs\?"), lambda route: route.fulfill(**list_dirs))
        page.reload()
        self.wait_ready(page)
        page.locator("#settings-open-btn").click()
        page.locator(".settings-nav-item[data-tab='files']").click()
        page.locator(".browser-dir-btn[data-target='setting-content-src']").click()

    def wait_until(self, page, condition: str, message: str, arg=None, polling="raf") -> None:
        """
        JS の条件（関数の式）が true を返すまで待つ。expect と同じ上限（wait_ms）であきらめ、AssertionError（message）で落とす
        （locator の expect で書けない条件、たとえばスクロールの位置や 2 つの要素の高さの差に使う）
        """
        api = import_playwright()
        try:
            page.wait_for_function(condition, arg=arg, timeout=self.wait_ms, polling=polling)
        except api.TimeoutError:
            raise AssertionError(message) from None

    @staticmethod
    @contextmanager
    def precondition():
        """
        直っていない不具合のテスト（xfail(strict=True, raises=AssertionError)）で、不具合の手前の準備を確かめる囲み

        ここで落ちたら AssertionError ではなく失敗（pytest.fail）にする。準備が崩れた（セレクタが変わった等）のに、
        「まだ直っていない」として xfail で黙って通り、直ったことに気づけなくなるのを防ぐ。
        xfail のテストの書き方の約束（CLAUDE.md の Testing にも書いた）:
        - 不具合の判定は、AssertionError で落ちる書き方にする（expect・assert・wait_until）。click・wait_for_url などの
          操作が落ちたとき（Playwright の TimeoutError）は、raises に当たらないので xfail に吸われず失敗になる
        - reason には、ロードマップの ID と、証拠にする状態（どの画面で何をすると、何がどうなっているか）を書く
        - 判定はこの囲みに入れない。入れると、直っていない今の落ち方まで失敗になり、直ったときの XPASS も判定できない。
          囲むのは、どう直しても成り立つ準備だけにする（直し方しだいで変わる状態は、判定の側で見る）
        """
        try:
            yield
        except AssertionError as error:
            pytest.fail(f"不具合の手前の準備が崩れた（xfail で隠さない）: {error}")


@pytest.fixture
def e2e(request, e2e_browser, e2e_servers, e2e_vault, monkeypatch):
    """
    E2E のサイト（E2ESite）。テスト用のノートを置き、管理用ポートのサーバーを管理者とみなす

    ADMIN_PORT の差し替えはこのテストのあいだだけ（TestClient のテストは base_url の 8001 を管理者とみなしているので、漏らさない）。
    xfail の印が付いたテストでは、expect と wait_until の上限を E2E_XFAIL_WAIT_MS にする（expect の設定は全体に効くので、
    終わったら必ず既定に戻す）。
    終わったらブラウザの context を閉じ、開いたページに JS のエラーと CSP の違反が無かったこと・書き込みを止めなかったことを確かめる
    """
    expect = import_playwright().expect
    marked_xfail = request.node.get_closest_marker("xfail") is not None
    monkeypatch.setattr(helpers, "ADMIN_PORT", e2e_servers.admin_port)
    site = E2ESite(browser=e2e_browser, servers=e2e_servers,
                   wait_ms=E2E_XFAIL_WAIT_MS if marked_xfail else E2E_WAIT_MS)
    if marked_xfail:
        expect.set_options(timeout=E2E_XFAIL_WAIT_MS)
    try:
        yield site
    finally:
        if marked_xfail:
            expect.set_options(timeout=None)    # None で Playwright の既定（5 秒）に戻る
        for context in site.contexts:
            context.close()
    assert not site.errors, f"ページで JS のエラーが出た: {site.errors}"
    assert not site.csp_violations, (
        f"ページで CSP の違反が出た（インラインのスクリプト・eval などを足していないか。S-10）: {site.csp_violations}")
    assert not site.blocked, f"書き込みのリクエストを止めた（テストが送ってはいけない）: {site.blocked}"
