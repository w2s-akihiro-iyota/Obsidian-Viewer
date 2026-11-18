"""ノートの HTML のサニタイズ（app/core/html_sanitizer.py・S-10）の契約テスト

ノートに書いた生の HTML は、描画（render_markdown）の最後に、許可したタグと属性だけに作り直す。
内部リンクなどアプリの出力も Markdown の変換の前に本文へ差し込むので、描き終わった HTML 全体にかける。
- 危ないもの（script・on*・javascript: などの URL・hx-*・iframe・form・style の url(javascript:) など）は出力に残らない
- 中身ごと捨てる要素（script・iframe・textarea など）は、入れ子になっていても中身を残さない
- 閉じていないタグは最後に閉じ、開いていない閉じタグ（</div></article> など）は捨てる（本文の枠の外に出られない）
- アプリが出す HTML（内部リンク・埋め込み・コールアウト・カードリンク・Dataview・タグ・数式・Mermaid・タスク・表の寄せ）と、
  よく使う HTML（br・details・span の style・u・font・img など）は、描画結果が変わらない
- HTML に無いタグ（List<T> の <T>・<think> など）は、捨てずに元のタグの文字のまま見せる（R4）
- 山かっこの中にコロンがある文字（<ASP:RadioButton>）は自動リンクにせず、R4 で文字のまま見せる
（記事ページ・リンクのプレビュー・エディタのプレビューがサニタイズした HTML を返すことは tests/test_api.py）
"""
import re
from html import unescape
from html.parser import HTMLParser

import pytest

from app.core.html_sanitizer import sanitize_html
from app.core.markdown import CALLOUT_ICONS, md
from app.services import content
from app.services.content import _NOTE_ICON_SVG, render_markdown
from app.services.images import image_html
from conftest import RAW_HTML_ATTACKS, RAW_HTML_MARK, RAW_HTML_NOTE, RAW_HTML_PARTNER_NOTE

# 出力に出てよいタグ（アプリの出力とよく使う HTML。svg の中はアイコンの部品だけ）。
# サニタイザーの出力を独立に検算するための写し。サニタイザーの許可リストを import して使うと、
# 許可リストに危ないタグを足してもテストが一緒に変わって気づけないので、わざと書き写している
_SAFE_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "caption", "cite", "code", "col", "colgroup", "dd", "del", "details", "div",
    "dl", "dt", "em", "figcaption", "figure", "font", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "input",
    "ins", "kbd", "li", "mark", "ol", "p", "pre", "q", "rp", "rt", "ruby", "s", "samp", "small", "span", "strong",
    "sub", "summary", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul", "var", "wbr",
    "svg", "path", "circle", "polyline", "line", "rect", "polygon",
}
# 出力の属性の値に出てはいけない URL の scheme（空白・制御文字を除き、小文字にして見る）
_BAD_SCHEMES = ("javascript:", "vbscript:", "data:", "file:")
# 出力の style に出てはいけないプロパティ（ページの部品の上に重ねて見せられるもの）
_OVERLAY_PROPERTIES = {"position", "z-index", "inset", "top", "left", "right", "bottom", "transform", "display"}


# サニタイズの出力のタグの形（属性の値はダブルクォートで囲み、中に < > " を含まない）。
# HTMLParser の読み方に頼らず、出力の文字列そのものを見る（ブラウザとパーサーの読み方の違いに左右されない）
_OUTPUT_TAG_RE = re.compile(r'<(/?)([a-zA-Z][a-zA-Z0-9]*)((?:\s+[a-zA-Z][a-zA-Z0-9-]*(?:="[^"<>]*")?)*)\s*/?>')
_OUTPUT_ATTR_RE = re.compile(r'([a-zA-Z][a-zA-Z0-9-]*)(?:="([^"<>]*)")?')


def assert_safe(html: str) -> None:
    """
    出力が、許可したタグと属性だけでできている

    - タグの形でない < > が残っていない（文字はすべてエスケープ済み。ブラウザがタグとして読む所は、下で調べたタグだけ）
    - タグは許可したものだけ。イベント属性（on*）・hx-*・data-* が無い
    - href・src・style に javascript: などの危ない scheme や expression が無い
    """
    assert "<" not in _OUTPUT_TAG_RE.sub("", html) and ">" not in _OUTPUT_TAG_RE.sub("", html), html
    for m in _OUTPUT_TAG_RE.finditer(html):
        tag = m.group(2).lower()
        assert tag in _SAFE_TAGS, (tag, html)
        for name, value in _OUTPUT_ATTR_RE.findall(m.group(3)):
            name = name.lower()
            assert not name.startswith(("on", "hx-", "data-")), (tag, name, html)
            if name in ("href", "src", "style"):
                compact = "".join(ch for ch in unescape(value) if ch > " ").lower()
                assert not any(s in compact for s in _BAD_SCHEMES), (tag, name, value)
                assert "expression" not in compact, (tag, name, value)
            if name == "style":
                properties = {decl.split(":", 1)[0].strip().lower() for decl in unescape(value).split(";") if ":" in decl}
                assert not properties & _OVERLAY_PROPERTIES, (tag, value)


# 閉じタグの無い要素（_Tokens で、開きタグだけで終わる要素として扱う）。これも検算用の写しで、出力に出うるもの
# （br・hr・img・input・col・wbr）と、念のため HTML の主な void 要素を入れている。
# サニタイザーの _VOID_ELEMENTS にある廃止された要素（image・keygen など）は出力に出ないので入れていない
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Tokens(HTMLParser):
    """HTML を、ブラウザから見た中身（タグ・属性・文字）の並びにする（書き方の違い <br /> と <br>・&quot; と " は区別しない）"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens: list[tuple] = []
        self._open: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tokens.append(("start", tag, tuple(attrs)))
        if tag not in _VOID:
            self._open.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.tokens.append(("start", tag, tuple(attrs)))
        if tag not in _VOID:
            self.tokens.append(("end", tag))

    def handle_endtag(self, tag):
        # 開いていない閉じタグはブラウザも無視するので、並びに入れない
        if tag not in self._open:
            return
        while self._open:
            top = self._open.pop()
            self.tokens.append(("end", top))
            if top == tag:
                break

    def handle_data(self, data):
        if self.tokens and self.tokens[-1][0] == "text":
            self.tokens[-1] = ("text", self.tokens[-1][1] + data)
        else:
            self.tokens.append(("text", data))


def tokens(html: str) -> list[tuple]:
    parser = _Tokens()
    parser.feed(html)
    parser.close()
    return parser.tokens


# ---------- 危ないものは残らない ----------

@pytest.mark.parametrize("src, expected", [
    # スクリプト
    ("<script>alert(1)</script>", ""),
    ('<ScRiPt src="//evil.example/x.js"></sCrIpT>後', "後"),
    ("<svg><script>alert(1)</script></svg>", "<svg></svg>"),
    # イベント属性
    ("<img src=x onerror=alert(1)>", '<img src="x">'),
    ('<img src="x" ONERROR="alert(1)" alt="a">', '<img src="x" alt="a">'),
    ('<svg onload="alert(1)"></svg>', "<svg></svg>"),
    ('<div/onclick="alert(1)">x</div>', "<div>x</div>"),
    ('<a href="/view/x" onmouseover="alert(1)">x</a>', '<a href="/view/x">x</a>'),
    # 引用符の崩れ（属性の名前に紛れ込ませる）
    ('<img src="x" alt="a"onerror="alert(1)">', '<img src="x" alt="a">'),
    ('<a href="x"" onclick="alert(1)">y</a>', '<a href="x">y</a>'),
    # 別の文書・プラグイン・フォーム・ページの設定を変えるもの
    ('<iframe src="https://evil.example/"></iframe>後', "後"),
    ('<iframe srcdoc="<script>alert(1)</script>"></iframe>後', "後"),
    ('<object data="x.swf"><param name="a" value="b"></object>後', "後"),
    ('<embed src="x.swf">後', "後"),
    ('<form action="https://evil.example/"><input name="p"><button>送信</button></form>後', "後"),
    ('<meta http-equiv="refresh" content="0;url=https://evil.example/">後', "後"),
    ('<base href="https://evil.example/">後', "後"),
    ('<link rel="stylesheet" href="https://evil.example/x.css">後', "後"),
    ("<style>body{display:none}</style>後", "後"),
    ("<template><img src=x onerror=alert(1)></template>後", "後"),
    ('<math><mi xlink:href="javascript:alert(1)">x</mi></math>後', "後"),
    ('<frameset><frame src="https://evil.example/"></frameset>後', "後"),
    ("<select><option>a</option></select>後", "後"),
    ("<xmp><img src=x onerror=alert(1)></xmp>後", "後"),
    # htmx の属性（hx-* / data-hx-*）
    ('<div hx-get="/api/sync/run" hx-trigger="load" data-hx-post="/x" data-hx-trigger="load">x</div>', "<div>x</div>"),
    # 中身ごと捨てる要素の中に隠したもの・入れ子
    ("<textarea><img src=x onerror=alert(1)></textarea>後", "後"),
    ("<title><img src=x onerror=alert(1)></title>後", "後"),
    ('<noscript><p title="</noscript><img src=x onerror=alert(1)>"></noscript>後', "後"),
    ("<object><object></object><img src=x onerror=alert(1)></object>後", "後"),
    # コメントで隠したもの
    ("<!-- <img src=x onerror=alert(1)> -->後", "後"),
    # 閉じていないタグ（最後まで閉じない開きタグは、ブラウザと同じく捨てる）
    ("前<img src=x onerror=alert(1)", "前"),
    # 本文の枠の外へ出ようとする閉じタグ
    ('</div></article><div class="evil">x</div>', '<div class="evil">x</div>'),
    # svg の中のスクリプトになりうる部品
    ("<svg><foreignObject><img src=x onerror=alert(1)></foreignObject></svg>", "<svg></svg>"),
    ('<svg><a href="javascript:alert(1)"><text>x</text></a></svg>', "<svg></svg>"),
    ('<svg><animate attributeName="href" values="javascript:alert(1)"/><set attributeName="onmouseover" to="alert(1)"/>'
     '<use href="data:image/svg+xml,x"/></svg>', "<svg></svg>"),
    ("<svg><style><img src=x onerror=alert(1)></style></svg>", "<svg></svg>"),
    # 属性の値・文字の中のタグは、文字のまま
    ('<div title="&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;">x</div>',
     '<div title="&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;">x</div>'),
    ("&lt;script&gt;alert(1)&lt;/script&gt;", "&lt;script&gt;alert(1)&lt;/script&gt;"),
])
def test_危ないタグと属性を出力に残さない(src, expected):
    out = sanitize_html(src)
    assert out == expected
    assert_safe(out)


@pytest.mark.parametrize("src", [
    "<!--><img src=x onerror=alert(1)>-->",
    "<p>a</p><!-- x --!><img src=x onerror=alert(1)>",
    "<svg><![CDATA[><img src=x onerror=alert(1)>]]></svg>",
    "<scr<script>ipt>alert(1)</script>",
    "<<img src=x onerror=alert(1)>",
    '<img """><script>alert(1)</script>">',
    "</script><script>alert(1)</script>",
    "<img src=x:alert(alt) onerror=eval(src) alt=0>",
    '<div style="x:expression(alert(1))" onclick=alert(1)>x</div>',
    "<img src=x onerror=alert(1)//",
    '<a href="https://example.com"\nonclick="alert(1)">x</a>',
])
def test_崩れた書き方でも危ないものを残さない(src):
    # 読み方は Python の版で細かく違うことがあるので、出力の形ではなく危ないものが無いことだけを見る
    out = sanitize_html(src)
    assert_safe(out)
    assert "<script" not in out.lower()


@pytest.mark.parametrize("href", [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    " javascript:alert(1)",
    "\tjavascript:alert(1)",
    "java\tscript:alert(1)",
    "java\nscript:alert(1)",
    "java&#x09;script:alert(1)",
    "java&Tab;script:alert(1)",
    "&#106;avascript:alert(1)",
    "&#x6A;avascript:alert(1)",
    "&#0000106;avascript:alert(1)",
    "javas&#99;ript:alert(1)",
    "javascript&colon;alert(1)",
    "\x01javascript:alert(1)",
    "vbscript:msgbox(1)",
    "data:text/html,&lt;script&gt;alert(1)&lt;/script&gt;",
    "file:///etc/passwd",
    ":alert(1)",
])
def test_リンク先のURLはhttpとhttpsとmailtoとobsidianとサイト内だけ残す(href):
    assert sanitize_html(f'<a href="{href}">x</a>') == "<a>x</a>"


@pytest.mark.parametrize("href", [
    "obsidian://open?vault=Obsidian-DB&amp;file=a.md",
    "obsidian://adv-uri?vault=v&amp;filepath=003_Notes%2Fa.md",
    "OBSIDIAN://open?vault=v",
])
def test_obsidianのリンクはhrefに残す(href):
    # Obsidian のアプリを開くだけでスクリプトは動かない（ユーザーの決定）
    assert sanitize_html(f'<a href="{href}">x</a>') == f'<a href="{href}">x</a>'


@pytest.mark.parametrize("src", ["javascript:alert(1)", "data:image/svg+xml,&lt;svg onload=alert(1)&gt;", "file:///x.png",
                                 "mailto:a@example.com", "obsidian://open?vault=v"])
def test_画像のURLはhttpとhttpsとサイト内だけ残す(src):
    assert sanitize_html(f'<img src="{src}" alt="a">') == '<img alt="a">'


@pytest.mark.parametrize("style", [
    "width:expression(alert(1))",
    "width:ex/**/pression(alert(1))",
    "background:url(javascript:alert(1))",
    "background:url(&quot;javascript:alert(1)&quot;)",
    "background:url('data:image/svg+xml,x')",
    "background:url(x.png)",
    "background:url(https://ok.example/x.png",
    "background:\\75 rl(javascript:alert(1))",
    "background:u\\72l(javascript:alert(1))",
    "background-image:image-set('javascript:alert(1)' 1x)",
    "@import 'https://evil.example/x.css'",
    "behavior:url(x.htc)",
    "-moz-binding:url(https://evil.example/x.xml#x)",
])
def test_危ない書き方を含むstyleは属性ごと捨てる(style):
    assert sanitize_html(f'<span style="{style}">x</span>') == "<span>x</span>"


@pytest.mark.parametrize("style", [
    "background:#fff3a3",
    "text-align:center",
    "page-break-after: always;",
    "color: red; font-weight: bold",
    "background-image: url(&quot;https://example.com/i.png&quot;)",
    "background-color: rgba(255, 0, 0, 0.3); color: #333",
    "font-size: 120%; font-style: italic; font-family: &quot;Noto Sans JP&quot;, sans-serif",
    "text-decoration: underline wavy red; vertical-align: middle",
    "page-break-before: always; break-after: page; break-inside: avoid",
    "font-family: &quot;a;b&quot;",
])
def test_ふつうのstyleは残す(style):
    assert sanitize_html(f'<span style="{style}">x</span>') == f'<span style="{style}">x</span>'


@pytest.mark.parametrize("style, expected", [
    # ページの部品の上に重ねて見せられるプロパティは、その宣言だけ落とす
    ("color: red; position: fixed", "color: red"),
    ("position:fixed;top:0;left:0;right:0;bottom:0;inset:0;z-index:9999;background:#fff",
     "background:#fff"),
    ("transform: translateY(-100px); font-weight: bold; display: none", "font-weight: bold"),
    ("font-weight: bold; margin-top: -500px; width: 100vw; height: 100vh; opacity: 0", "font-weight: bold"),
    ("COLOR: Red; Position: Fixed", "COLOR: Red"),
])
def test_styleは許可したプロパティの宣言だけを残す(style, expected):
    assert sanitize_html(f'<span style="{style}">x</span>') == f'<span style="{expected}">x</span>'


@pytest.mark.parametrize("style", [
    "position: fixed; top: 0; left: 0; z-index: 9999",
    "display: none",
    "visibility: hidden",
    "--x: 1",
    "posit\\ion: fixed",
    "color: red /* ; position: fixed */",
    "font-family: &quot;a; position: fixed",
    "color: red; background: url(https://ok.example/a.png",
    ";;",
    "color",
])
def test_許可したプロパティの宣言が残らないstyleは属性ごと捨てる(style):
    assert sanitize_html(f'<span style="{style}">x</span>') == "<span>x</span>"


@pytest.mark.parametrize("src, expected", [
    ('<a href="https://example.com" target="_blank" rel="opener">x</a>',
     '<a href="https://example.com" target="_blank" rel="noopener noreferrer">x</a>'),
    ('<a href="https://example.com" target="_top">x</a>', '<a href="https://example.com">x</a>'),
    ('<a href="https://example.com" rel="opener">x</a>', '<a href="https://example.com">x</a>'),
])
def test_新しいタブで開くリンクにはnoopenerを付けほかのtargetは捨てる(src, expected):
    assert sanitize_html(src) == expected


@pytest.mark.parametrize("src, expected", [
    ('<input type="text" value="x">後', "後"),
    ('<input value="x">後', "後"),
    ('<input type="checkbox" checked onclick="alert(1)" name="x" value="y">', '<input type="checkbox" checked>'),
])
def test_inputはチェックボックスだけ残す(src, expected):
    assert sanitize_html(src) == expected


def test_idは見出しだけに残す():
    # ほかの要素の id は、ページの部品の id と同じ名前にして DOM を乗っ取れる（DOM clobbering）ので捨てる
    assert sanitize_html('<p id="x">a</p><h2 id="y">b</h2><img id="z" src="/a.png">') == '<p>a</p><h2 id="y">b</h2><img src="/a.png">'


def test_閉じていない要素は最後に閉じる():
    assert sanitize_html("<div><span>a") == "<div><span>a</span></div>"


@pytest.mark.parametrize("src, expected", [
    # ファイルの終わりまで閉じない（ノートの残りが全部消えないよう、開きタグを文字にして後ろを読み直す）
    ("<select>本文の続き", "&lt;select&gt;本文の続き"),
    ("前<textarea>後ろ<b>太</b>", "前&lt;textarea&gt;後ろ<b>太</b>"),
    ("<title>題\n\n<p>本文</p>", "&lt;title&gt;題\n\n<p>本文</p>"),
    ('<iframe src="https://evil.example/">続き', "&lt;iframe src=&quot;https://evil.example/&quot;&gt;続き"),
    ("<form><button>押す", "&lt;form&gt;&lt;button&gt;押す"),
    ("<script>alert(1)", "&lt;script&gt;alert(1)"),
    ("<object><object></object>続き", "&lt;object&gt;続き"),
    ("1行目\n2行目 <select>\n3行目<b>太</b>", "1行目\n2行目 &lt;select&gt;\n3行目<b>太</b>"),
    ("<p>前</p>\r\n<p><button>押す</p>", "<p>前</p>\r\n<p>&lt;button&gt;押す</p>"),
    # 外側の要素が先に閉じた（ちゃんと閉じていないので、同じく文字にして読み直す）
    ("<p>前<button>押す</p><p>後</p>", "<p>前&lt;button&gt;押す</p><p>後</p>"),
    ("<div><form>a<img src=x onerror=alert(1)></div>後", '<div>&lt;form&gt;a<img src="x"></div>後'),
    # ちゃんと閉じたものは中身ごと捨てる
    ("<select><option>a</option></select>後", "後"),
])
def test_閉じていない中身ごと捨てる要素は開きタグを文字にして後ろを読み直す(src, expected):
    out = sanitize_html(src)
    assert out == expected
    assert_safe(out)


def test_閉じていない中身ごと捨てる要素がたくさんあっても終わる():
    # 1 つずつ文字にして読み直すので、読み直しの回数は閉じていない開きタグの数で止まる
    src = "<select>a" * 200
    assert sanitize_html(src) == "&lt;select&gt;a" * 200


# ---------- よく使う HTML とアプリの出力は残る ----------

@pytest.mark.parametrize("src", [
    "表<br>セル",
    "表<br />セル",
    "<details><summary>要約</summary><p>中身</p></details>",
    "<details open><summary>要約</summary>中身</details>",
    '<span style="background:#fff3a3">印</span>',
    '<div style="page-break-after: always;"></div>',
    "<u>下線</u>",
    '<font color="red">赤</font>',
    '<img src="/media/a.png">',
    '<img src="https://example.com/a.png" alt="a" width="100">',
    '<sub>1</sub><sup>2</sup><kbd>Ctrl</kbd><small>小</small><b>太</b><i>斜</i><del>消</del><ins>挿</ins>'
    '<abbr title="HyperText Markup Language">HTML</abbr><mark>印</mark>',
    '<a href="mailto:a@example.com">m</a>',
    '<a href="#節">x</a>',
    '<a href="?q=1">x</a>',
    '<a href="./x.md">x</a>',
    '<a href="//example.com/x">x</a>',
    '<a href="https://example.com/?a=1&amp;b=2">x</a>',
    '<table><tr><td colspan="2" rowspan="1">x</td></tr></table>',
    '<ol start="3"><li>x</li></ol>',
    '<p align="center">中央</p>',
])
def test_よく使うHTMLはそのまま残す(src):
    assert sanitize_html(src) == src


def test_内部リンクのアイコンとリンク切れはそのまま残す():
    src = (f'<a href="/view/x" class="internal-link">{_NOTE_ICON_SVG}名前</a>'
           '<span class="internal-link-broken">無いノート</span>')
    assert sanitize_html(src) == src


@pytest.mark.parametrize("kind", sorted(CALLOUT_ICONS))
def test_コールアウトのアイコンはそのまま残す(kind):
    src = f'<div class="callout-icon">{CALLOUT_ICONS[kind]}</div>'
    # danger のアイコンには開いていない </polygon> がある（ブラウザも無視する）。それだけは捨てる
    assert sanitize_html(src) == src.replace("</polygon>", "")


def test_埋め込みの画像はそのまま残す():
    src = image_html("/media/a%20b.png", "a b.png", "100x50")
    assert sanitize_html(src) == src


def test_カードリンクはそのまま残す():
    src = md.render("```cardlink\nurl: https://example.com/?a=1&b=2\ntitle: 題\ndescription: 説明\n"
                    "image: https://example.com/i.png\n```\n")
    assert 'class="link-card"' in src and "link-card-image" in src
    assert sanitize_html(src) == src


def test_タスクのチェックボックスと表の寄せはそのまま残す():
    src = md.render("- [ ] 未\n- [x] 済\n\n| 左 | 中 | 右 |\n|:--|:-:|--:|\n| a | b | c |\n")
    assert "task-list-item-checkbox" in src and 'style="text-align:center"' in src
    assert sanitize_html(src) == src


def test_文字の中の記号は描画と同じエスケープのまま():
    src = md.render('a & b < c > d "e"\n\n```\n<script>x</script>\n```\n')
    assert sanitize_html(src) == src


# ---------- R4: HTML に無いタグは文字のまま見せる ----------

@pytest.mark.parametrize("src, expected", [
    ("<p>List<T> を返す</p>", "<p>List&lt;T&gt; を返す</p>"),
    ("<think>考える</think>", "&lt;think&gt;考える&lt;/think&gt;"),
    ("Vec<String> と <id>", "Vec&lt;String&gt; と &lt;id&gt;"),
    ("<setting key value />", "&lt;setting key value /&gt;"),
    ("<ratex-formula>x^2</ratex-formula>", "&lt;ratex-formula&gt;x^2&lt;/ratex-formula&gt;"),
    ('<foo onclick="alert(1)">', "&lt;foo onclick=&quot;alert(1)&quot;&gt;"),
    ('<path d="M0 0"/>', "&lt;path d=&quot;M0 0&quot;/&gt;"),
    # 閉じタグも書いたときの大文字小文字のまま（html.parser は名前を小文字にして渡すので、元の文字を使う）
    ("<T>型</T>", "&lt;T&gt;型&lt;/T&gt;"),
    ("<Think>考える</Think>", "&lt;Think&gt;考える&lt;/Think&gt;"),
    ("考える</Think >終わり", "考える&lt;/Think &gt;終わり"),
])
def test_HTMLに無いタグは元の文字のまま出す(src, expected):
    out = sanitize_html(src)
    assert out == expected
    assert_safe(out)


def test_html_parserは閉じタグをparse_endtagの中でhandle_endtagに渡す():
    """
    サニタイザーは HTMLParser.parse_endtag を上書きして、R4 の閉じタグの元の文字（</Think>）を取っている。
    その前提（parse_endtag があり、handle_endtag はその中から呼ばれ、閉じタグの終わりの位置を返す）を確かめる。
    Python の版を上げたときに落ちたら、_SafeHtmlRebuilder.parse_endtag の作りを見直す
    """
    calls = []

    class Probe(HTMLParser):
        inside = None

        def parse_endtag(self, i):
            self.inside = i
            try:
                end = super().parse_endtag(i)
            finally:
                self.inside = None
            calls.append(("parse_endtag", self.rawdata[i:end]))
            return end

        def handle_endtag(self, tag):
            calls.append(("handle_endtag", tag, self.inside is not None))

    probe = Probe(convert_charrefs=True)
    probe.feed("a</Think >b")
    probe.close()
    assert calls == [("handle_endtag", "think", True), ("parse_endtag", "</Think >")]


@pytest.mark.parametrize("src, expected", [
    ("<center>中央</center>", "中央"),
    ("<article>本文</article>", "本文"),
    ("<label><b>名前</b></label>", "<b>名前</b>"),
])
def test_HTMLにあるが許可していないタグは外して中身を残す(src, expected):
    assert sanitize_html(src) == expected


# ---------- render_markdown を通した結果 ----------

_CALLOUTS = "\n\n".join(f"> [!{kind}] 題\n> 本文" for kind in CALLOUT_ICONS)
# アプリの記法を全部使った本文。プラグイン（app/core/markdown.py・app/services/wikilinks.py・app/core/dataview.py・
# app/services/images.py）が出す HTML を変えたり、記法を足したりしたら、ここにその記法を足す
# （サニタイズで落ちるタグ・属性・class があれば、test_アプリの記法の描画結果はサニタイズで変わらない が名指しで落ちる）
_PARTNER = RAW_HTML_PARTNER_NOTE[:-3]
_APP_FEATURES = f"""# 見出し
## 節 #タグ
[[{_PARTNER}]] [[{_PARTNER}#節|別名]] [[無いノート]] [[#見出し]] [[非公開]]

![[{_PARTNER}]]

![[{_PARTNER}#節]]

![[{_PARTNER}#無い節]]

![[pic.png|100x50]] ![[pic.png]] ![[無い.png]]

![alt](https://example.com/a.png "t") [link](https://example.com "tt") <https://auto.example.com> [rel](./x.md) [m](mailto:a@example.com)

<obsidian://open?vault=v&file=f> <a@example.com> [o](obsidian://open?vault=v)

**強** *弱* ~~消~~ ==印== `code`

3. 三
4. 四

- [ ] 未
- [x] 済

| 左 | 中 | 右 | 無 |
|:--|:-:|--:|---|
| a | b | c | d |

> 引用

---

$x^2$

$$
y = 1
$$

```mermaid
graph TD; A-->B
```

```python
print("<b>")
```

```cardlink
url: https://example.com/?a=1&b=2
title: タイトル
description: 説明
image: https://example.com/i.png
```

```cardlink
url: ftp://example.com/
title: t
```

```dataview
TABLE done, flag, tags, missing FROM ""
```

```dataview
LIST FROM #t1
```

```dataview
FOO
```

```ad-note
title: 題
本文
```

{_CALLOUTS}
"""


def _render_without_sanitizer(monkeypatch, body, published_only):
    """サニタイズをかけない描画（アプリの出力そのもの）"""
    with monkeypatch.context() as m:
        m.setattr(content, "sanitize_html", lambda html: html, raising=False)
        return render_markdown(body, published_only=published_only, source_path="描画.md")


class _Vocabulary(HTMLParser):
    """HTML で使われているタグ・属性・class を集める（"tag"・"tag[attr]"・"tag.class"）"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.words: set[str] = set()

    def handle_starttag(self, tag, attrs):
        self.words.add(tag)
        for name, value in attrs:
            self.words.add(f"{tag}[{name}]")
            if name == "class":
                self.words.update(f"{tag}.{cls}" for cls in (value or "").split())

    handle_startendtag = handle_starttag


def vocabulary(html: str) -> set[str]:
    parser = _Vocabulary()
    parser.feed(html)
    parser.close()
    return parser.words


@pytest.mark.parametrize("published_only", [False, True])
def test_アプリの記法の描画結果はサニタイズで変わらない(raw_html_site, monkeypatch, published_only):
    html = render_markdown(_APP_FEATURES, published_only=published_only, source_path="描画.md")
    raw = _render_without_sanitizer(monkeypatch, _APP_FEATURES, published_only)
    # 記法が全部描かれていること（テストの前提）
    for mark in ('class="internal-link"', "internal-link-icon", "internal-link-broken", "markdown-embed-content",
                 "markdown-embed-missing", 'id="embed1_', "obsidian-image", 'class="inline-tag"', "contains-task-list",
                 'style="text-align:center"', "math inline", "math block", "language-mermaid", 'class="link-card"',
                 "link-card-image", "dataview-table", "dataview-list-link", "dataview-note-icon", "dataview-tag",
                 "dataview-null", "dataview-badge-true", "dataview-badge-false", "dataview-error", "callout-danger",
                 'start="3"', 'href="mailto:a@example.com"', 'href="obsidian://open?vault=v&amp;file=f"',
                 'href="obsidian://open?vault=v"'):
        assert mark in raw, mark
    # アプリが出したタグ・属性・class のうち、サニタイズで落ちたもの（許可リストの足し忘れ）
    dropped = vocabulary(raw) - vocabulary(html)
    assert not dropped, f"許可リストに足す: {sorted(dropped)}"
    # 値や文字も含めて、ブラウザから見た中身が同じ
    assert tokens(html) == tokens(raw)


def test_ノートに書いた危ないHTMLは描画結果に残らない(raw_html_site):
    html = render_markdown(RAW_HTML_ATTACKS, published_only=False)
    assert RAW_HTML_MARK not in html
    assert "hx-get" not in html
    assert_safe(html)


def test_埋め込んだノートの危ないHTMLも残らない(raw_html_site):
    html = render_markdown(f"![[{RAW_HTML_NOTE[:-3]}]]", published_only=True)
    assert "markdown-embed-content" in html
    assert RAW_HTML_MARK not in html
    assert_safe(html)


def test_よく使うHTMLは描画結果に残る(raw_html_site):
    body = ("| 列 |\n|---|\n| 1行目<br>2行目 |\n\n<details><summary>要約</summary>\n\n中身\n\n</details>\n\n"
            '<span style="background:#fff3a3">印</span> <u>下線</u> <font color="red">赤</font>\n\n'
            '<div style="page-break-after: always;"></div>\n')
    html = render_markdown(body, published_only=False)
    for part in ("<td>1行目<br>2行目</td>", "<details><summary>要約</summary>", "</details>",
                 '<span style="background:#fff3a3">印</span>', "<u>下線</u>", '<font color="red">赤</font>',
                 '<div style="page-break-after: always;"></div>'):
        assert part in html, part


def test_HTMLに無いタグは描画結果で文字のまま見える(raw_html_site):
    html = render_markdown("List<T> を返す\n\n<think>\n考える\n</think>\n", published_only=False)
    assert "List&lt;T&gt; を返す" in html
    assert "&lt;think&gt;" in html and "&lt;/think&gt;" in html
    assert "<T>" not in html and "<think>" not in html


@pytest.mark.parametrize("src, shown", [
    ("<ASP:RadioButton> を置く", "&lt;ASP:RadioButton&gt; を置く"),
    ("<w2cm:RadioButtonGroup>", "&lt;w2cm:RadioButtonGroup&gt;"),
])
def test_山かっこの中にコロンがある文字は自動リンクにせず文字のまま見える(raw_html_site, src, shown):
    # 自動リンクにすると < > が消え、href はサニタイズで落ちて、押せない文字だけが残っていた
    html = render_markdown(src, published_only=False)
    assert shown in html
    assert "<a" not in html
