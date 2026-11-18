"""ページの CSP（S-10）の契約テスト（ブラウザでの動きは tests/test_e2e_csp.py）

- 画面の HTML（どちらのポートも・エラー画面の 404・403・500・素の HTML も）に CSP を付ける
  - script-src は 'self' と先読み（F-15）の hash 1 つだけ。'unsafe-inline'・'unsafe-eval'・'inline-speculation-rules' は入れない
  - upgrade-insecure-requests は付けない（LAN の http の配信が壊れる）
- JSON・静的ファイルには付けない。添付（/media）は今までどおり sandbox だけ（すでに CSP がある応答には付けない）
- 先読みの speculationrules は hash で許す。ページに出した中身の hash がポリシーと一致する
- 画面にはインラインのスクリプト・イベント属性・HTMX の eval を使う書き方を置かない（CSP で動かなくなる）
"""
import base64
import hashlib
import html
import json
import re

import pytest
from fastapi.testclient import TestClient

from app import cache
from app.api import content as content_api
from app.api import errors as errors_api
from app.core import indexing
from app.main import app

ADMIN = "http://localhost:8001"
PUBLIC = "http://localhost:8000"
BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
CSP = "content-security-policy"

# script-src 以外の指示（合意したポリシー）。script-src は _assert_page_policy で見る
EXPECTED_DIRECTIVES = {
    "default-src": ["'self'"],
    "style-src": ["'self'", "'unsafe-inline'"],    # Mermaid の SVG の中の style 要素・style 属性
    "img-src": ["'self'", "https:"],               # カードリンクの外の画像
    "font-src": ["'self'"],
    "connect-src": ["'self'"],
    "media-src": ["'self'"],
    "frame-src": ["'none'"],
    "object-src": ["'none'"],
    "base-uri": ["'none'"],
    "form-action": ["'self'"],
    "frame-ancestors": ["'none'"],
}
SPECULATION_RULES_RE = re.compile(r'<script type="speculationrules">(.*?)</script>', re.S)

# 画面（ブラウザで開くページ）。{slug} は公開.md のスラッグ
PAGES = [
    (ADMIN, "/"), (PUBLIC, "/"),
    (ADMIN, "/view/{slug}"), (PUBLIC, "/view/{slug}"),
    (ADMIN, "/graph"), (PUBLIC, "/graph"),
    (ADMIN, "/dashboard"), (ADMIN, "/editor"),
]
# エラー画面（ブラウザで開いたとき）
ERROR_PAGES = [
    (PUBLIC, "/view/無いノート", 404),
    (ADMIN, "/存在しないURL", 404),
    (PUBLIC, "/dashboard", 403),
]


@pytest.fixture
def site(tmp_path, use_test_vault, isolated_caches):
    notes, media = tmp_path / "vault", tmp_path / "media"
    notes.mkdir()
    media.mkdir()
    (notes / "公開.md").write_text("---\npublish: true\n---\n公開の本文\n", encoding="utf-8")
    (media / "page.html").write_text("<script>alert(1)</script>", encoding="utf-8")
    use_test_vault(notes, media)
    indexing.refresh_global_caches()
    return tmp_path


def _get(base, path, **kwargs):
    client = TestClient(app, base_url=base, raise_server_exceptions=False)
    return client.get(path.format(slug=cache.PATH_TO_SLUG.get("公開.md", "")), headers=BROWSER, **kwargs)


def _directives(policy: str) -> dict[str, list[str]]:
    parsed = {}
    for part in policy.split(";"):
        name, *values = part.split()
        parsed[name] = values
    return parsed


def _hash_source(text: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii") + "'"


def _assert_page_policy(res) -> None:
    """ページの CSP が付いていて、合意したポリシーになっている"""
    assert res.headers["content-type"].startswith("text/html")
    directives = _directives(res.headers[CSP])
    script_src = directives.pop("script-src")
    assert script_src[0] == "'self'" and len(script_src) == 2 and script_src[1].startswith("'sha256-"), (
        f"script-src は 'self' と先読みの hash だけ: {script_src}")
    assert directives == EXPECTED_DIRECTIVES, "upgrade-insecure-requests などを足していないか"


# ---------- CSP を付ける応答 ----------

@pytest.mark.parametrize("base, path", PAGES)
def test_画面のHTMLにはCSPを付ける(site, base, path):
    res = _get(base, path)
    assert res.status_code == 200
    _assert_page_policy(res)


@pytest.mark.parametrize("base, path, status", ERROR_PAGES)
def test_エラー画面にもCSPを付ける(site, base, path, status):
    res = _get(base, path)
    assert res.status_code == status
    _assert_page_policy(res)


def _boom(*args, **kwargs):
    raise RuntimeError("boom")


def test_500のエラー画面にもCSPを付ける(site, monkeypatch):
    # 想定外の例外は ServerErrorMiddleware が一番外で受けるので、アプリのミドルウェアを通らない
    monkeypatch.setattr(content_api, "build_note_list", _boom)
    res = _get(PUBLIC, "/")
    assert res.status_code == 500
    _assert_page_policy(res)


def test_エラー画面の描画に失敗した素のHTMLにもCSPを付ける(site, monkeypatch):
    monkeypatch.setattr(content_api, "build_note_list", _boom)
    monkeypatch.setattr(errors_api.templates, "TemplateResponse", _boom)
    res = _get(PUBLIC, "/")
    assert res.status_code == 500 and "<!DOCTYPE html>" in res.text
    _assert_page_policy(res)


# ---------- CSP を付けない応答 ----------

@pytest.mark.parametrize("path, headers", [
    ("/api/tree", {}),                         # JSON
    ("/view/無いノート", {"Accept": "*/*"}),     # ブラウザで開いたのでなければエラーも JSON
    ("/static/css/style.css", {}),             # 静的ファイル
])
def test_JSONと静的ファイルにはページのCSPを付けない(site, path, headers):
    res = TestClient(app, base_url=ADMIN).get(path, headers=headers)
    assert not res.headers["content-type"].startswith("text/html")
    assert CSP not in res.headers


def test_添付のHTMLは今までどおりsandboxだけ(site):
    res = TestClient(app, base_url=ADMIN).get("/media/page.html")
    assert res.status_code == 200
    assert res.headers[CSP] == "sandbox", "すでに CSP がある応答に、ページの CSP を足さない"


# ---------- 先読みの hash ----------

@pytest.mark.parametrize("base, path", [(ADMIN, "/"), (PUBLIC, "/view/{slug}"), (PUBLIC, "/view/無いノート")])
def test_先読みのhashはページに出した中身と一致する(site, base, path):
    res = _get(base, path)
    (rules,) = SPECULATION_RULES_RE.findall(res.text)
    assert _directives(res.headers[CSP])["script-src"][1] == _hash_source(rules), (
        "base.html の speculationrules の中身（空白も含む）と CSP の hash がずれている")


# ---------- 画面の書き方（インラインのスクリプトを置かない） ----------

@pytest.mark.parametrize("base, path", PAGES + [(PUBLIC, "/view/無いノート")])
def test_画面にインラインのスクリプトとイベント属性とHTMXのevalを置かない(site, base, path):
    text = _get(base, path).text
    inline_scripts = [tag for tag in re.findall(r"<script\b[^>]*>", text)
                      if " src=" not in tag and tag != '<script type="speculationrules">']
    assert inline_scripts == [], "インラインの script は CSP で動かない。static/js/ のファイルにする"
    assert re.findall(r"<[a-zA-Z][^>]*\son[a-z]+\s*=", text) == [], "イベント属性（onload= など）は CSP で動かない"
    # HTMX のイベント名の直後の [...] のフィルタ・hx-on・hx-vars・js: は eval が要る（htmx-config で allowEval を切っている）。
    # from:[...] の [...] は CSS のセレクタなので eval は要らない
    assert re.findall(r'hx-trigger="[^"]*[\w-]\[', text) == []
    assert re.findall(r"""hx-on|hx-vars|hx-vals=["']\s*(?:js|javascript):""", text) == []


def test_HTMXはevalとscriptタグの実行を切る(site):
    text = _get(ADMIN, "/").text
    (content,) = re.findall(r"<meta name=\"htmx-config\" content='([^']*)'>", text)
    config = json.loads(html.unescape(content))
    assert config == {"allowEval": False, "allowScriptTags": False}, "inlineScriptNonce も設定しない"
