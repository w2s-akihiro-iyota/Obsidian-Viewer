"""Obsidian 記法のリンクと埋め込み（app/services/images.py・app/core/markdown.py）の契約テスト

B-1: [[ノート#見出し]]・[[#見出し]]・[[フォルダ/ノート]] がリンク切れにならない
F-4: ![[ノート]]・![[ノート#見出し]] の埋め込み
"""
import os
import time

import pytest

from app import cache
from app.core.markdown import heading_anchor
from app.core.indexing import _build_link_maps, resolve_note_path
from app.services import images, wikilinks
from app.services.content import render_markdown
from app.services.publish_check import check_publish


def media_index_of(*names: str) -> images.MediaIndex:
    """直下にファイル名だけを置いた添付の索引（描画・振り分けのテスト用）"""
    return images.MediaIndex(paths=frozenset(names), by_name={n: n for n in names},
                             by_lower_name={n.lower(): n for n in names}, by_lower_path={n.lower(): n for n in names})


@pytest.fixture
def vault(tmp_path, monkeypatch):
    notes = {
        "会議/定例.md": "---\npublish: true\n---\n# 定例\n冒頭\n## 議題\n議題の本文\n### 詳細\n詳細の本文\n## 決定事項\n決定の本文\n",
        "公開メモ.md": "---\npublish: true\n---\n公開メモの本文\n",
        "秘密.md": "---\npublish: false\n---\n秘密の本文\n",
        "ループA.md": "---\npublish: true\n---\nA本文 ![[ループB]]\n",
        "ループB.md": "---\npublish: true\n---\nB本文 ![[ループA]]\n",
        "段1.md": "---\npublish: true\n---\n段1本文\n\n![[段2]]\n",
        "段2.md": "---\npublish: true\n---\n段2本文\n\n![[段3]]\n",
        "段3.md": "---\npublish: true\n---\n段3本文\n",
    }
    published = {"会議/定例.md", "公開メモ.md", "ループA.md", "ループB.md", "段1.md", "段2.md", "段3.md"}
    for rel, text in notes.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    monkeypatch.setattr(wikilinks, "CONTENT_DIR", tmp_path)
    monkeypatch.setattr(cache, "GLOBAL_FILE_CACHE", [{"path": r, "published": r in published} for r in notes])
    monkeypatch.setattr(cache, "FILE_NAME_CACHE", {os.path.splitext(os.path.basename(r))[0]: r for r in notes})
    monkeypatch.setattr(cache, "PATH_TO_SLUG", {r: r[:-3].replace("/", "/") for r in notes})
    monkeypatch.setattr(cache, "MEDIA_INDEX", None)
    return tmp_path


def render(src, published_only=False):
    return render_markdown(src, published_only=published_only)


# ---------- 見出しの ID ----------

def test_見出しにIDが付く():
    html = render("## 議題\n本文")
    assert f'id="{heading_anchor("議題")}"' in html


def test_同じ見出しが続くと番号で区別する():
    html = render("## 議題\n## 議題\n")
    a = heading_anchor("議題")
    assert f'id="{a}"' in html and f'id="{a}-1"' in html


def test_装飾つきの見出しも文字だけでIDを作る():
    assert heading_anchor("**重要** な点") == heading_anchor("重要 な点")


# ---------- B-1: リンク ----------

def test_見出しリンクはその位置へ飛ぶ(vault):
    html = render("[[定例#議題]]")
    assert 'class="internal-link-broken"' not in html
    assert f'href="/view/会議/定例#{heading_anchor("議題")}"' in html.replace("%E8%AD%B0%E9%A1%8C", "議題")
    assert "定例 &gt; 議題" in html or "定例 > 議題" in html


def test_別名つきの見出しリンクは別名を表示する(vault):
    html = render("[[定例#議題|今日の議題]]")
    assert "今日の議題" in html and "internal-link-broken" not in html


def test_同じノート内の見出しリンク(vault):
    html = render("[[#決定事項]]")
    assert 'href="#' in html and "internal-link-broken" not in html


def test_パス指定のリンク(vault):
    html = render("[[会議/定例]]")
    assert 'href="/view/会議/定例"' in html


def test_無いノートはリンク切れ表示(vault):
    assert "internal-link-broken" in render("[[無いノート#見出し]]")


def test_外部向けには非公開ノートへのリンクを出さない(vault):
    html = render("[[秘密]]", published_only=True)
    assert "internal-link-broken" in html and "/view/秘密" not in html


# ---------- F-4: 埋め込み ----------

def test_ノート全体を埋め込む(vault):
    html = render("![[公開メモ]]")
    assert "markdown-embed" in html and "公開メモの本文" in html
    assert "publish" not in html  # frontmatter は出さない


def test_見出しの節だけを埋め込む(vault):
    html = render("![[定例#議題]]")
    assert "議題の本文" in html and "詳細の本文" in html  # 下位の見出しは含む
    assert "決定の本文" not in html and "冒頭" not in html


def test_見出しが無ければその旨を出す(vault):
    html = render("![[定例#無い見出し]]")
    assert "markdown-embed" in html and "見出しが見つかりません" in html


def test_互いに埋め込むループは止まる(vault):
    html = render("![[ループA]]")
    assert "A本文" in html and "B本文" in html
    assert html.count("A本文") == 1


def test_入れ子は2段まで(vault):
    html = render("![[段1]]")
    assert "段1本文" in html and "段2本文" in html
    assert "段3本文" not in html  # 3段目は埋め込まずリンクにする
    assert "/view/段3" in html


def test_外部向けには非公開ノートを埋め込まない(vault):
    html = render("![[秘密]]", published_only=True)
    assert "秘密の本文" not in html and "/view/秘密" not in html


def test_埋め込んだノートを依存として記録する(vault):
    deps = set()
    render_markdown("![[段1]]", published_only=False, deps=deps)
    assert deps == {"段1.md", "段2.md"}


def test_画像の埋め込みは今までどおり(vault, monkeypatch):
    monkeypatch.setattr(cache, "MEDIA_INDEX", media_index_of("a.png"))
    html = render("![[a.png|300]]")
    assert '<img src="/media/a.png" alt="a.png" width="300"' in html


def test_ノートのページから描画しても2段まで埋め込める(vault):
    html = render_markdown("![[段1]]", published_only=False, source_path="ページ.md")
    assert "段2本文" in html and "段3本文" not in html


def test_自分自身は埋め込まずリンクにする(vault):
    html = render_markdown("![[公開メモ]]", published_only=False, source_path="公開メモ.md")
    assert "markdown-embed" not in html and "/view/公開メモ" in html


def test_コードの中は置き換えない(vault):
    html = render("```\n![[公開メモ]]\n```\n`[[定例]]`")
    assert "markdown-embed" not in html and "/view/会議/定例" not in html


def test_画像のサイズ指定は数字だけを受け付ける(vault, monkeypatch):
    monkeypatch.setattr(cache, "MEDIA_INDEX", media_index_of("a.png"))
    html = render('![[a.png|300" onerror="alert(1)]]')
    assert "onerror" not in html and "<img" in html
    assert 'width="300" height="200"' in render("![[a.png|300x200]]")


def test_索引が古くてもファイルが非公開なら外部向けに埋め込まない(vault):
    # 索引上は公開のまま、ファイルだけ非公開に変わった状態
    (vault / "公開メモ.md").write_text("---\npublish: false\n---\n公開メモの本文\n", encoding="utf-8")
    html = render("![[公開メモ]]", published_only=True)
    assert "公開メモの本文" not in html


def _add_note(vault, name, text):
    (vault / f"{name}.md").write_text(text, encoding="utf-8")
    cache.FILE_NAME_CACHE[name] = f"{name}.md"
    cache.PATH_TO_SLUG[f"{name}.md"] = name


def test_コードブロック内の見出し記号は節の区切りにしない(vault):
    _add_note(vault, "コード", "## 手順\n```bash\n# コメント\n```\n手順の続き\n## 次\n次の本文\n")
    html = render("![[コード#手順]]")
    assert "手順の続き" in html and "次の本文" not in html


def test_同じ見出しが複数あれば最初の節を埋め込む(vault):
    _add_note(vault, "重複", "## 議題\n1つ目\n## 議題\n2つ目\n")
    html = render("![[重複#議題]]")
    assert "1つ目" in html and "2つ目" not in html


def test_見出しにリンクがあっても表示される文字でIDを作る():
    assert heading_anchor("[[定例|今日の定例]] の件") == heading_anchor("今日の定例 の件")
    assert heading_anchor("[資料](https://example.com) まとめ") == heading_anchor("資料 まとめ")


# ---------- リンクの解決ルール（描画側とバックリンク側で共通） ----------

def test_リンクの解決はファイル名かパス指定():
    names = {"定例": "会議/定例.md"}
    slugs = {"会議/定例.md": "x", "会議/別.md": "y"}
    assert resolve_note_path("定例", names, slugs) == "会議/定例.md"
    assert resolve_note_path("定例.md", names, slugs) == "会議/定例.md"
    assert resolve_note_path("会議/別", names, slugs) == "会議/別.md"
    assert resolve_note_path("無い", names, slugs) is None


def test_バックリンクもパス指定と見出しつきリンクを数える(vault, monkeypatch):
    bodies = {"参照元.md": "[[会議/定例]] と [[段1#見出し]]"}
    files = [{"path": "参照元.md", "title": "参照元"}]
    _, forward = _build_link_maps(files, bodies, cache.FILE_NAME_CACHE, dict(cache.PATH_TO_SLUG))
    assert set(forward["参照元.md"]) == {"会議/定例.md", "段1.md"}


def test_Admonitionの入れ子があっても後ろの見出しの節を埋め込める(vault):
    # ```ad-question の中に ```ad-success があり、閉じる ``` は 1 つだけ（sample.md と同じ形）
    _add_note(vault, "入れ子", (
        "## 前\n```ad-question\ntitle: Q\n```ad-success\ntitle: S\n```\n\n"
        "```python\nprint(1)\n```\n## 目当て\n目当ての本文\n## 後\n後の本文\n"
    ))
    html = render("![[入れ子#目当て]]")
    assert "目当ての本文" in html and "後の本文" not in html
    assert "見出しが見つかりません" not in html


def test_後ろに文字がある区切り行ではコードブロックを閉じない(vault):
    # ```text の中の ```python は中身。閉じるのは何も書いていない ``` だけ
    html = render("```text\n```python\n[[定例]]\n```\n[[定例]]")
    assert html.count('href="/view/会議/定例"') == 1


# ---------- Q-10: リンク走査の共通化（描画とバックリンクで同じ判定） ----------

def test_走査はリンクの種類と名前と見出しと別名を返す():
    links = list(wikilinks.iter_wikilinks("[[会議/定例#議題|今日]] と ![[a.png|300]] と [[#決定事項]]"))
    assert [(link.is_embed, link.name, link.heading, link.alias) for link in links] == [
        (False, "会議/定例", "議題", "今日"),
        (True, "a.png", "", "300"),
        (False, "", "決定事項", None),
    ]


def test_走査はコードブロックとインラインコードとコールアウト内のコードを飛ばす():
    src = (
        "```\n[[コード1]]\n```\n"
        "`[[コード2]]` の後ろの [[本物1]]\n"
        "> [!note]\n> ```\n> [[コード3]]\n> ```\n"
        "> [[本物2]]\n"
    )
    assert [link.name for link in wikilinks.iter_wikilinks(src)] == ["本物1", "本物2"]


def test_コードの中のリンクはバックリンクにもフォワードリンクにも入らない(vault, monkeypatch):
    bodies = {"参照元.md": "```\n[[公開メモ]]\n```\n`[[段1]]`\n> ```\n> ![[段2]]\n> ```\n[[会議/定例]]\n"}
    files = [{"path": "参照元.md", "title": "参照元"}]
    backlinks, forward = _build_link_maps(files, bodies, cache.FILE_NAME_CACHE, dict(cache.PATH_TO_SLUG))
    assert forward["参照元.md"] == ["会議/定例.md"]
    assert set(backlinks) == {"会議/定例.md"}


def test_バックリンクは埋め込みも数え自己リンクと重複を除く(vault, monkeypatch):
    bodies = {"参照元.md": "![[公開メモ]] [[公開メモ|別名]] [[参照元]]"}
    names = dict(cache.FILE_NAME_CACHE, 参照元="参照元.md")
    slugs = dict(cache.PATH_TO_SLUG, **{"参照元.md": "参照元"})
    files = [{"path": "参照元.md", "title": "参照元"}]
    backlinks, forward = _build_link_maps(files, bodies, names, slugs)
    assert forward["参照元.md"] == ["公開メモ.md"]
    assert backlinks["公開メモ.md"] == [{"title": "参照元", "path": "参照元.md", "slug": "参照元"}]
    assert "参照元.md" not in backlinks


# ---------- リンクの振り分け（classify_link）と走査の境界 ----------

def _published_paths():
    return {f["path"] for f in cache.GLOBAL_FILE_CACHE if f.get("published")}


@pytest.fixture
def only_a_png(monkeypatch):
    """static に a.png だけがある状態"""
    monkeypatch.setattr(cache, "MEDIA_INDEX", media_index_of("a.png"))


@pytest.mark.parametrize("src, kind, rendered, field, listed", [
    # 名前も見出しも空。描画は中身の無いリンク切れ（画面には何も出ない）なので、公開チェックでも挙げない
    ("[[#]]", "MISSING_NOTE", '<span class="internal-link-broken"></span>', None, None),
    # 別名つきの画像。| の後ろは表示サイズ
    ("![[a.png|300]]", "IMAGE", '<img src="/media/a.png" alt="a.png" width="300"', None, None),
    ("![[無い.png|300]]", "MISSING_IMAGE", '<span class="internal-link-broken">無い.png</span>', "missing_images", "無い.png"),
    # 見出しつきの画像名はノートの節の埋め込みとして扱われ、そのノートが無いのでリンク切れ
    ("![[a.png#x]]", "MISSING_NOTE", '<span class="internal-link-broken">a.png &gt; x</span>', "missing_links", "a.png"),
])
def test_境界のリンクも描画と公開チェックで同じに振り分ける(vault, only_a_png, src, kind, rendered, field, listed):
    link = next(wikilinks.iter_wikilinks(src))
    assert wikilinks.classify_link(link, _published_paths()).kind is wikilinks.LinkKind[kind]
    assert rendered in render(src, published_only=True)
    result = check_publish("x.md", src, True)
    if field:
        assert getattr(result, field) == (listed,) and result.issue_count == 1
    else:
        assert result.issue_count == 0


def test_閉じないコードブロックの後ろのリンクは数えない(vault):
    src = "[[公開メモ]]\n```\n[[秘密]]\n[[無いノート]]\n"
    assert [link.name for link in wikilinks.iter_wikilinks(src)] == ["公開メモ"]
    html = render(src, published_only=True)
    assert "internal-link-broken" not in html and html.count('class="internal-link"') == 1
    assert check_publish("x.md", src, True).issue_count == 0
