"""Markdown の独自記法（app/core/markdown.py）の契約テスト

レンダリング結果の HTML で確かめる。
- callout: > [!type] タイトル を div.callout にする
- Admonition: ```ad-type のフェンスを callout の記法（> [!TYPE]）に書き換える
- cardlink: ```cardlink のフェンスをリンクカードにする
- mark: ==text== を <mark> にする
"""
import pytest

from app.core.markdown import CALLOUT_ICONS, md, process_admonition_blocks


# ---------- mark ----------

def test_イコール2つで囲むとmarkにする():
    assert "<mark>強調</mark>" in md.render("==強調==")


def test_閉じないイコールはそのまま():
    html = md.render("==未閉じ")
    assert "<mark>" not in html
    assert "==未閉じ" in html


def test_インラインコードの中はmarkにしない():
    assert md.render("`==x==`").strip() == "<p><code>==x==</code></p>"


def test_1行に複数のmarkを置ける():
    html = md.render("==a== と ==b==")
    assert html.count("<mark>") == 2


# ---------- callout ----------

def test_calloutは種類のクラスとタイトルと本文の枠を持つ():
    html = md.render("> [!tip] タイトル\n> 本文")
    assert '<div class="callout callout-tip">' in html
    assert '<div class="callout-title">' in html
    assert CALLOUT_ICONS["tip"] in html
    assert "タイトル</div>" in html
    assert '<div class="callout-content"><p>本文</p>' in html
    assert "<blockquote>" not in html


def test_calloutのタイトルを省くと種類名を先頭大文字で出す():
    assert "Note</div>" in md.render("> [!note]\n> 本文")


def test_calloutの種類は小文字にそろえる():
    assert '<div class="callout callout-warning">' in md.render("> [!WARNING] 注意\n> 本文")


def test_知らない種類のcalloutはnoteのアイコンを使う():
    html = md.render("> [!custom-x] 題\n> 本文")
    assert '<div class="callout callout-custom-x">' in html
    assert CALLOUT_ICONS["note"] in html


def test_普通の引用はcalloutにしない():
    html = md.render("> 普通の引用")
    assert "<blockquote>" in html
    assert "callout" not in html


def test_入れ子のcalloutは内側も外側の本文の中に置く():
    html = md.render("> [!note] 外\n> > [!tip] 内\n> > 内の本文")
    outer = html.index('class="callout callout-note"')
    inner = html.index('class="callout callout-tip"')
    assert outer < inner
    assert "内の本文" in html


# ---------- Admonition（process_admonition_blocks） ----------

def test_Admonitionはcalloutの記法に書き換えtitle行を題にする():
    src = "```ad-note\ntitle: 題\n本文\n```"
    assert process_admonition_blocks(src) == "> [!NOTE] 題\n> 本文"


def test_Admonitionのtitleを省くと種類名を題にする():
    assert process_admonition_blocks("```ad-tip\n本文\n```") == "> [!TIP] Tip\n> 本文"


def test_Admonitionの中のコードブロックは引用の中に残す():
    src = "````ad-warning\ntitle: 注意\n```py\nx = 1\n```\n````\n後ろ"
    assert process_admonition_blocks(src) == "> [!WARNING] 注意\n> ```py\n> x = 1\n> ```\n後ろ"


def test_Admonitionの入れ子は引用を重ねる():
    src = "````ad-note\n外\n```ad-tip\n内\n```\n````"
    assert process_admonition_blocks(src) == "> [!NOTE] Note\n> 外\n> > [!TIP] Tip\n> > 内"


def test_Admonitionの無い本文は変えない():
    src = "# 見出し\n\n```python\nx = 1\n```\n本文"
    assert process_admonition_blocks(src) == src


def test_Admonitionはcalloutとして描画される():
    html = md.render(process_admonition_blocks("```ad-bug\ntitle: 既知の不具合\n本文\n```"))
    assert '<div class="callout callout-bug">' in html
    assert "既知の不具合</div>" in html


# いまの振る舞い（不具合候補）: コードブロックの中の ```ad- の行も Admonition の始まりとみなし、
# コードの中身を書き換える（markdown.py:218 で、コードブロックの中かどうかを見ずに ad- を判定している）。
def test_いまはコードブロックの中のad行も書き換える():
    assert process_admonition_blocks("```md\n```ad-note\n```") == "```md\n> [!NOTE] Note\n```"


# ---------- cardlink ----------

def test_cardlinkはリンクカードにしタイトルと説明とURLと画像を出す():
    html = md.render("```cardlink\nurl: https://example.com/a?b=1\ntitle: 例のページ\n"
                     "description: 説明\nimage: https://example.com/i.png\n```")
    assert '<a href="https://example.com/a?b=1" class="link-card" target="_blank" rel="noopener noreferrer">' in html
    assert '<div class="link-card-title">例のページ</div>' in html
    assert '<div class="link-card-description">説明</div>' in html
    assert '<div class="link-card-meta">https://example.com/a?b=1</div>' in html
    assert 'style="background-image: url(https://example.com/i.png)"' in html
    assert "<pre>" not in html


def test_cardlinkのタイトルと画像を省くとNoTitleで画像の枠を出さない():
    html = md.render("```cardlink\nurl: https://example.com\n```")
    assert '<div class="link-card-title">No Title</div>' in html
    assert "link-card-image" not in html


def test_cardlinkのURLを省くとシャープにリンクする():
    assert '<a href="#" class="link-card"' in md.render("```cardlink\ntitle: 題\n```")


@pytest.mark.parametrize("info", ["python", ""])
def test_cardlink以外のコードブロックは通常どおりエスケープして出す(info):
    html = md.render(f"```{info}\nx = \"<b>\"\n```")
    assert "<pre><code" in html
    assert "&lt;b&gt;" in html
    assert "link-card" not in html
