"""Vault の添付の配信（S-5）の契約テスト

- 管理者（管理用ポート）は MEDIA_DIR の添付を全部見られる
- 外部の人（公開用ポート）は、公開ノートが参照する添付とアプリ同梱のサンプル（_viewer-samples/）だけ。
  それ以外は 404（403 にしない＝存在を知らせない）。Vault 側の samples/ のような名前は無条件には出さない
  - 参照の数え方: 本文の ![[...]]（描画で画像になるもの。見出しつき・コードの中は数えない）、![](/media/...)、
    <img src="/media/...">、frontmatter の image / thumbnail（名前・[[名前]]・![[名前|300]]・/media/ の URL）
- MEDIA_DIR の外（..・%2e%2e・絶対パス・外を指すシンボリックリンク）と、存在しないものは管理者でも 404
- 応答には nosniff と CSP sandbox。画像以外（html・pdf 等）はダウンロード（attachment）。svg は <img> で出せるよう inline
- 描画が出す画像の URL は、外部の人にもすべて 200（描画と許可リストの引き方がそろっている）
- OGP 画像は許可リストと同じ抽出で選ぶ（コードの中を拾わない・タイトルを混ぜない）
- 索引の作り直しに失敗したら、許可リストを空にする（fail-closed）
- 起動時の引っ越し: static/images のアプリの部品（logo.png・samples/）以外を MEDIA_DIR へ移す。消えて困るので、
  移し先に違う中身があれば元を残す
"""
import os
import re
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app import cache
from app.api import content as content_api
from app.api import editor as editor_api
from app.api import media as media_api
from app.config import MEDIA_SAMPLES_DIR_NAME
from app.core import indexing
from app.main import app
from app.services import media_migration, wikilinks
from app.services.images import MediaIndex
from app.services.media_access import (first_image_href, frontmatter_media_rel, is_public_media, note_media_refs,
                                       resolve_media_file)
from app.services.media_migration import migrate_legacy_media

ADMIN = "http://localhost:8001"
PUBLIC = "http://localhost:8000"
SAMPLE = f"{MEDIA_SAMPLES_DIR_NAME}/s.png"

_PUBLIC_NOTE = (
    "---\npublish: true\nimage: \"[[表紙.png]]\"\n---\n"
    "![[公開画像.png|300]]\n"
    "![説明](</media/sub/md 画像.png> \"タイトル\")\n"
    '<img src="/media/HTML%E7%94%BB%E5%83%8F.png" alt="x">\n'
    "![[Upper]]\n"
    "![[見出し付き.png#見出し]]\n"
    "![[子ノート]]\n"
    "```\n![[コード内.png]]\n```\n"
    "`![](/media/インライン.png)`\n"
)
_NOTES = {
    "公開.md": _PUBLIC_NOTE,
    "子ノート.md": "---\npublish: true\n---\n![[子の画像.png]]\n",
    "非公開.md": "---\npublish: false\n---\n![[秘密画像.png]] ![[公開画像.png]]\n",
    "サムネ.md": "---\npublish: true\nthumbnail: /media/サムネ.png\n---\n本文\n",
    "表紙2.md": "---\npublish: true\nimage: \"![[表紙2.png|300]]\"\n---\n本文\n",
    "ogp.md": "---\npublish: true\n---\n```\n![[コード内.png]]\n```\n![a](/media/公開画像.png \"t\") ![[子の画像.png]]\n",
}

_PUBLIC_FILES = ("公開画像.png", "sub/md 画像.png", "HTML画像.png", "表紙.png", "表紙2.png", "サムネ.png",
                 "UPPER.PNG", "子の画像.png", SAMPLE)
_HIDDEN_FILES = ("秘密画像.png", "未参照.png", "コード内.png", "インライン.png", "見出し付き.png", "samples/vault.png")
_OTHER_FILES = ("page.html", "evil.svg", "doc.pdf")


@pytest.fixture
def media_site(tmp_path, monkeypatch):
    """公開ノート・非公開ノートと、それぞれが参照する添付を置いた Vault"""
    vault, media = tmp_path / "vault", tmp_path / "media"
    vault.mkdir()
    for name in ("GLOBAL_FILE_CACHE", "GLOBAL_FILE_TREE_CACHE", "GLOBAL_FILE_TREE_CACHE_PUBLIC", "MEDIA_INDEX",
                 "PUBLIC_MEDIA_PATHS", "MARKDOWN_CACHE", "FILE_NAME_CACHE", "BACKLINK_CACHE", "FORWARD_LINK_CACHE",
                 "SEARCH_INDEX", "SLUG_TO_PATH", "PATH_TO_SLUG"):
        monkeypatch.setattr(cache, name, getattr(cache, name))
    for module in (content_api, editor_api, indexing, wikilinks):
        monkeypatch.setattr(module, "CONTENT_DIR", vault)
    monkeypatch.setattr(indexing, "MEDIA_DIR", media)
    monkeypatch.setattr(media_api, "MEDIA_DIR", media)

    for rel, text in _NOTES.items():
        (vault / rel).write_text(text, encoding="utf-8")
    for rel in _PUBLIC_FILES + _HIDDEN_FILES + _OTHER_FILES:
        p = media / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"img:" + rel.encode("utf-8"))
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    indexing.refresh_global_caches()
    return tmp_path


def _get(client, rel):
    return client.get("/media/" + quote(rel))


def _view(client, path):
    return client.get(f"/view/{cache.PATH_TO_SLUG[path]}").text


# ---------- 誰に何を見せるか ----------

def test_管理者は非公開ノートの添付も参照されない添付も見られる(media_site):
    client = TestClient(app, base_url=ADMIN)
    for rel in _PUBLIC_FILES + _HIDDEN_FILES:
        res = _get(client, rel)
        assert res.status_code == 200, rel
        assert res.content == b"img:" + rel.encode("utf-8")


@pytest.mark.parametrize("rel", _PUBLIC_FILES)
def test_外部の人は公開ノートが参照する添付と同梱サンプルを見られる(media_site, rel):
    assert _get(TestClient(app, base_url=PUBLIC), rel).status_code == 200


@pytest.mark.parametrize("rel", _HIDDEN_FILES)
def test_外部の人には公開ノートが参照しない添付を404にする(media_site, rel):
    # 非公開ノートだけが参照・どこからも参照されない・コードの中・見出しつきの埋め込み・Vault 側の samples/
    assert _get(TestClient(app, base_url=PUBLIC), rel).status_code == 404


def test_HEADでも同じ判定をする(media_site):
    public = TestClient(app, base_url=PUBLIC)
    assert public.head("/media/" + quote("公開画像.png")).status_code == 200
    assert public.head("/media/" + quote("秘密画像.png")).status_code == 404


@pytest.mark.parametrize("url", [
    "/media/%2e%2e/secret.txt",
    "/media/..%2fsecret.txt",
    "/media/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "/media//etc/passwd",
    "/media/%2Fetc%2Fpasswd",
    "/media/無い.png",
    "/media/sub",
    "/media/",
])
def test_MEDIA_DIRの外と存在しないものは管理者にも404(media_site, url):
    assert TestClient(app, base_url=ADMIN).get(url).status_code == 404
    assert TestClient(app, base_url=PUBLIC).get(url).status_code == 404


def test_パスの解決はMEDIA_DIRの外に出ない(media_site):
    media = media_site / "media"
    assert resolve_media_file(media, "../secret.txt") is None
    assert resolve_media_file(media, str(media_site / "secret.txt")) is None
    assert resolve_media_file(media, "sub/../公開画像.png") == ((media / "公開画像.png").resolve(), "公開画像.png")


def test_外を指すシンボリックリンクは404(media_site):
    link = media_site / "media" / "link.png"
    try:
        os.symlink(media_site / "secret.txt", link)
    except (OSError, NotImplementedError):
        pytest.skip("シンボリックリンクを作れない環境")
    assert TestClient(app, base_url=ADMIN).get("/media/link.png").status_code == 404


# ---------- 応答のヘッダー（XSS 対策） ----------

@pytest.mark.parametrize("rel, attachment", [
    ("公開画像.png", False),
    ("evil.svg", False),     # <img> で表示できるよう inline のまま（sandbox でスクリプトは動かない）
    ("page.html", True),
    ("doc.pdf", True),
])
def test_添付の応答はnosniffとsandboxを付け画像以外はダウンロードにする(media_site, rel, attachment):
    res = _get(TestClient(app, base_url=ADMIN), rel)
    assert res.status_code == 200
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["content-security-policy"] == "sandbox"
    assert res.headers.get("content-disposition", "").startswith("attachment") == attachment


# ---------- 描画・OGP と許可リストがそろっている ----------

def test_外部向けの記事ページの画像のURLは外部の人も全部取れる(media_site):
    public = TestClient(app, base_url=PUBLIC)
    html = _view(public, "公開.md")
    srcs = set(re.findall(r'<img[^>]*\ssrc="(/media/[^"]+)"', html))
    # 埋め込みの画像・大文字小文字違い・公開ノートの埋め込みの中の画像
    assert {"/media/" + quote("公開画像.png"), "/media/UPPER.PNG", "/media/" + quote("子の画像.png")} <= srcs
    # 見出しつきの埋め込み・コードの中は画像にしない（許可リストにも入らない）
    assert not any(name in html for name in ("/media/" + quote("見出し付き.png"), "/media/" + quote("コード内.png")))
    for src in srcs:
        assert public.get(src).status_code == 200, src


@pytest.mark.parametrize("path, expected", [
    ("公開.md", "表紙.png"),           # frontmatter の "[[表紙.png]]"
    ("表紙2.md", "表紙2.png"),         # frontmatter の "![[表紙2.png|300]]"
    ("サムネ.md", "サムネ.png"),        # frontmatter の thumbnail（/media/ の URL）
    ("ogp.md", "公開画像.png"),         # 本文の最初の画像。コードの中は飛ばし、"t"（タイトル）を混ぜない
])
def test_OGP画像は許可リストと同じ抽出で選ぶ(media_site, path, expected):
    public = TestClient(app, base_url=PUBLIC)
    html = _view(public, path)
    src = "/media/" + quote(expected)
    assert f'<meta property="og:image" content="{PUBLIC}{src}">' in html
    assert public.get(src).status_code == 200


def test_ノートを非公開にすると添付も外部から見えなくなる(media_site):
    public = TestClient(app, base_url=PUBLIC)
    assert _get(public, "表紙.png").status_code == 200
    (media_site / "vault" / "公開.md").write_text(_PUBLIC_NOTE.replace("publish: true", "publish: false"),
                                                 encoding="utf-8")
    indexing.refresh_global_caches()
    assert _get(public, "表紙.png").status_code == 404
    assert _get(public, "UPPER.PNG").status_code == 404
    assert _get(public, SAMPLE).status_code == 200


def test_索引の作り直しに失敗したら許可リストを空にする(media_site, monkeypatch):
    public = TestClient(app, base_url=PUBLIC)
    assert cache.PUBLIC_MEDIA_PATHS and _get(public, "公開画像.png").status_code == 200

    def broken(notes):
        raise RuntimeError("壊れた")

    monkeypatch.setattr(indexing, "build_file_list", broken)
    with pytest.raises(RuntimeError):
        indexing.refresh_global_caches()
    assert cache.PUBLIC_MEDIA_PATHS == frozenset()
    assert _get(public, "公開画像.png").status_code == 404
    assert _get(public, SAMPLE).status_code == 200


# ---------- media_access の単体テスト（手組みの索引） ----------

def _index(*rels: str) -> MediaIndex:
    """相対パスから索引を手で組む"""
    names = {r.rsplit("/", 1)[-1]: r for r in reversed(rels)}
    return MediaIndex(
        paths=frozenset(rels),
        by_name=names,
        by_lower_name={n.lower(): r for n, r in names.items()},
        by_lower_stem={n.rsplit(".", 1)[0].lower(): r for n, r in names.items() if "." in n},
        by_lower_path={r.lower(): r for r in reversed(rels)},
    )


_IDX = _index("cover.png", "dir/図 1.png", "Photo.JPG", "x.png")


@pytest.mark.parametrize("value, expected", [
    ("cover.png", "cover.png"),
    ("cover", "cover.png"),                 # 拡張子なし
    ("[[cover.png]]", "cover.png"),
    ("![[cover.png|300]]", "cover.png"),
    ([["cover.png"]], "cover.png"),         # 引用符なしの [[cover.png]]（YAML では入れ子のリスト）
    ("/media/dir/%E5%9B%B3%201.png", "dir/図 1.png"),
    ("/media/PHOTO.jpg", "Photo.JPG"),      # 大文字小文字は索引の綴りにそろえる
    ("dir/図 1.png", "dir/図 1.png"),       # パス指定
    ("https://example.com/cover.png", None),
    ("/static/images/logo.png", None),
    ("無い.png", None),
    ("", None),
    (123, None),
])
def test_frontmatterの画像を添付に引く(value, expected):
    assert frontmatter_media_rel(value, _IDX) == expected


def test_ノートが参照する添付を拾う():
    body = (
        "![[cover.png]] ![[x.png#見出し]] ![[無い.png]]\n"
        "![a](</media/dir/図 1.png> \"t\") ![b](https://example.com/y.png) ![c](相対.png)\n"
        '<IMG alt="p" SRC="/media/photo.jpg">\n'
        "```\n![[x.png]]\n```\n`![[x.png]]`\n"
    )
    assert note_media_refs({}, body, _IDX) == {"cover.png", "dir/図 1.png", "Photo.JPG"}
    assert note_media_refs({"thumbnail": "x"}, "", _IDX) == {"x.png"}


def test_OGP画像は本文で最初に出てくる画像():
    assert first_image_href({}, "前 ![a](/media/x.png) 後 ![[cover.png]]", _IDX) == "/media/x.png"
    assert first_image_href({}, "![[cover.png]] ![a](/media/x.png)", _IDX) == "/media/cover.png"
    assert first_image_href({}, "```\n![[x.png]]\n```\n![b](https://example.com/y.png \"t\")",
                            _IDX) == "https://example.com/y.png"
    assert first_image_href({"image": "cover.png"}, "![[x.png]]", _IDX) == "/media/cover.png"
    assert first_image_href({"image": "無い.png"}, "![[x.png]]", _IDX) == "/media/x.png"
    assert first_image_href({}, "![[x.png#見出し]]", _IDX) is None


def test_外部に見せてよい添付の判定():
    public = frozenset({"cover.png", "Photo.JPG"})
    assert is_public_media(f"{MEDIA_SAMPLES_DIR_NAME}/a.png", frozenset(), _IDX)
    assert not is_public_media("samples/a.png", frozenset(), _IDX)
    assert is_public_media("cover.png", public, _IDX)
    assert not is_public_media("x.png", public, _IDX)
    # 大文字小文字を区別しないファイルシステムで、違う綴りで要求されたとき
    assert is_public_media("photo.jpg", public, _IDX)
    # 綴り違いの別のファイルが索引にある（区別するファイルシステム）なら読み替えない
    both = _index("A.png", "a.png")
    assert not is_public_media("A.png", frozenset({"a.png"}), both)


# ---------- 起動時の引っ越し ----------

def _write(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_アプリの部品以外をmediaへ移す(tmp_path):
    images, media = tmp_path / "static" / "images", tmp_path / "media"
    _write(images / "logo.png", b"logo")
    _write(images / "samples" / "help-display-settings.png", b"help")
    _write(images / "samples" / "sample-image.png", b"sample")
    _write(images / "写真.png", b"photo")
    _write(images / "フォルダ" / "深い" / "図.png", b"fig")

    result = migrate_legacy_media(images, media)

    assert (result.moved, result.dropped, result.kept) == (3, 0, 0)
    assert (media / "写真.png").read_bytes() == b"photo"
    assert (media / "フォルダ" / "深い" / "図.png").read_bytes() == b"fig"
    assert (media / MEDIA_SAMPLES_DIR_NAME / "sample-image.png").read_bytes() == b"sample"
    # アプリの部品は残す
    assert (images / "logo.png").exists() and (images / "samples" / "help-display-settings.png").exists()
    assert sorted(p.name for p in images.iterdir()) == ["logo.png", "samples"]
    assert not (images / "samples" / "sample-image.png").exists()
    # 一時ファイルを残さない
    assert not list(media.rglob("*.migrating"))


def test_移し先に同じ中身があれば元を消し違えば元を残す(tmp_path):
    images, media = tmp_path / "static" / "images", tmp_path / "media"
    _write(images / "同じ.png", b"same")
    _write(images / "違う.png", b"old")
    _write(images / "フォルダ" / "a.png", b"same-a")
    _write(images / "フォルダ" / "b.png", b"new-b")
    _write(media / "同じ.png", b"same")
    _write(media / "違う.png", b"current")
    _write(media / "フォルダ" / "a.png", b"same-a")

    result = migrate_legacy_media(images, media)

    assert (result.moved, result.dropped, result.kept) == (1, 2, 1)
    assert not (images / "同じ.png").exists() and not (images / "フォルダ").exists()
    # 中身が違えば、移し先はそのまま・元も残す
    assert (media / "違う.png").read_bytes() == b"current"
    assert (images / "違う.png").read_bytes() == b"old"
    assert (media / "フォルダ" / "b.png").read_bytes() == b"new-b"


def test_同じ名前のファイルがあるフォルダは移さず残す(tmp_path):
    images, media = tmp_path / "static" / "images", tmp_path / "media"
    _write(images / "名前" / "a.png", b"a")
    _write(media / "名前", b"file")
    result = migrate_legacy_media(images, media)
    assert result.kept == 1 and (images / "名前" / "a.png").exists()
    assert (media / "名前").read_bytes() == b"file"


def test_コピーに失敗したら元を残す(tmp_path, monkeypatch):
    images, media = tmp_path / "static" / "images", tmp_path / "media"
    _write(images / "写真.png", b"photo")

    def broken_copy(src, dst):
        _write(dst, b"ph")   # 途中で切れたコピー
        return dst

    monkeypatch.setattr(media_migration.shutil, "copy2", broken_copy)
    result = migrate_legacy_media(images, media)
    assert (result.moved, result.kept) == (0, 1)
    assert (images / "写真.png").read_bytes() == b"photo"
    assert not (media / "写真.png").exists() and not list(media.rglob("*.migrating"))


def test_移すものが無ければ何もしない(tmp_path):
    images, media = tmp_path / "static" / "images", tmp_path / "media"
    _write(images / "logo.png")
    _write(images / "samples" / "help-display-settings.png")
    result = migrate_legacy_media(images, media)
    assert (result.moved, result.dropped, result.kept) == (0, 0, 0)
    assert not media.exists()


def test_mediaをマウントしていないコンテナでは移さない(tmp_path, monkeypatch):
    """static だけマウントされている（古い docker-compose.yml のまま再起動した）ときは、移すと作り直しで消えるので移さない"""
    images, media = tmp_path / "static" / "images", tmp_path / "media"
    _write(images / "写真.png", b"photo")
    monkeypatch.setattr(media_migration.os.path, "ismount", lambda p: os.fspath(p) == os.fspath(images.parent))
    result = migrate_legacy_media(images, media)
    assert result.moved == 0 and (images / "写真.png").exists()
