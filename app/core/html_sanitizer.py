"""
ノートの描画結果（HTML）を、許可したタグと属性だけで作り直す（S-10）

ノートに書いた生の HTML（<script>・onerror・javascript: のリンクなど）を、記事ページ・プレビューで動かさないため。
内部リンク・埋め込みなどアプリの出力も Markdown の変換の前に本文へ差し込むので、トークンの上ではノートの生の HTML と
見分けられない。そこで描き終わった HTML 全体を html.parser で読み、次のやり方で出力を組み立て直す。

- 許可リスト（_ALLOWED_ATTRS）にあるタグと属性だけを出す。属性の値は必ずエスケープしてダブルクォートで囲む
- 文字は必ずエスケープして出す。コメント・doctype・処理命令・CDATA は捨てる
  （どんなに崩れた入力でも、出力は許可リストのタグと、エスケープした文字だけになる）
- 中身がスクリプト・別の文書・フォームなどになる要素（_DROP_WITH_CONTENT）は、自分の閉じタグで閉じたときだけ中身ごと捨てる。
  閉じないまま外側の要素が閉じたり本文が終わったりしたら、開きタグを文字にして、その後ろを読み直す（ノートの残りを消さない）
- 閉じていない要素は最後に閉じ、開いていない閉じタグは捨てる（本文の枠の外に出られない）
- HTML に無いタグ（List<T> の <T>・<think> など）は、捨てずに元のタグの文字をエスケープして出す（R4）。
  HTML にはあるが許可していないタグ（article・center など）は、タグだけ外して中身を残す
- svg はアプリのアイコンの部品（_SVG_CHILD_ATTRS）だけ。svg の中のほかの要素は中身ごと捨てる
- style は、許可したプロパティ（_STYLE_PROPERTIES）の宣言だけを残す
"""
import bisect
import re
from dataclasses import dataclass
from html.parser import HTMLParser

# 標準の HTML の要素名。これに無いタグは R4 で文字にする
# 出典: WHATWG HTML Living Standard の要素の一覧（https://html.spec.whatwg.org/multipage/indices.html の Elements）と、
# 廃止された要素（https://html.spec.whatwg.org/multipage/obsolete.html の Non-conforming features）。2026-11-18 に取得
_HTML_ELEMENTS = frozenset({
    "a", "abbr", "address", "area", "article", "aside", "audio", "b", "base", "bdi", "bdo", "blockquote", "body", "br",
    "button", "canvas", "caption", "cite", "code", "col", "colgroup", "data", "datalist", "dd", "del", "details", "dfn",
    "dialog", "div", "dl", "dt", "em", "embed", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3",
    "h4", "h5", "h6", "head", "header", "hgroup", "hr", "html", "i", "iframe", "img", "input", "ins", "kbd", "label",
    "legend", "li", "link", "main", "map", "mark", "math", "menu", "meta", "meter", "nav", "noscript", "object", "ol",
    "optgroup", "option", "output", "p", "picture", "pre", "progress", "q", "rp", "rt", "ruby", "s", "samp", "script",
    "search", "section", "select", "selectedcontent", "slot", "small", "source", "span", "strong", "style", "sub",
    "summary", "sup", "svg", "table", "tbody", "td", "template", "textarea", "tfoot", "th", "thead", "time", "title",
    "tr", "track", "u", "ul", "var", "video", "wbr",
    # 廃止された要素
    "acronym", "applet", "basefont", "bgsound", "big", "blink", "center", "dir", "font", "frame", "frameset", "isindex",
    "keygen", "listing", "marquee", "menuitem", "multicol", "nextid", "nobr", "noembed", "noframes", "param",
    "plaintext", "rb", "rtc", "spacer", "strike", "tt", "xmp",
    # 一覧には無いが、ブラウザが読み替える・埋め込みに使う要素（image は img に読み替える。fencedframe は WICG の仕様で iframe の仲間）
    "image", "fencedframe",
})

# 閉じタグの無い要素（開きタグだけで終わる。開いている要素の並びに積まない）
_VOID_ELEMENTS = frozenset({
    "area", "base", "basefont", "bgsound", "br", "col", "embed", "frame", "hr", "image", "img", "input", "isindex",
    "keygen", "link", "meta", "param", "source", "track", "wbr",
})

# 中身ごと捨てる要素（中身がスクリプト・スタイル・別の文書・プラグイン・フォームの部品になるもの）
_DROP_WITH_CONTENT = frozenset({
    "applet", "button", "datalist", "fencedframe", "form", "frameset", "iframe", "math", "noembed", "noframes",
    "noscript", "object", "optgroup", "option", "script", "select", "selectedcontent", "style", "template", "textarea",
    "title", "xmp",
})

# どの許可したタグにも付けてよい属性
_GLOBAL_ATTRS = frozenset({"class", "title", "style"})
_NO_ATTRS: frozenset[str] = frozenset()
# アプリの出力のタグに、ノートの書き方として足す属性（<p align="center">・<td colspan="2"> など）
_NOTE_ALIGN = frozenset({"align"})
_NOTE_CELL = frozenset({"colspan", "rowspan", "align"})
_HEADING_ATTRS = frozenset({"id"}) | _NOTE_ALIGN   # id は見出しのアンカー（heading_ids）。ほかの要素には付けない

# 許可するタグ → そのタグにだけ付けてよい属性（_GLOBAL_ATTRS に足す）。辞書は 1 つで、出どころで節に分ける
_ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    # ---------- アプリの出力 ----------
    # markdown-it（app/core/markdown.py の md。commonmark・table・strikethrough・mark・dollarmath・tasklists）:
    #   段落・見出し・リスト・引用・強調・表（寄せは style）・コード・リンク・画像・数式（span.math・div.math）・タスク（input）
    # app/core/markdown.py の独自の記法: コールアウト（div・svg）・カードリンク（a[target]・div[style]）・本文のタグ（a）
    # app/services/wikilinks.py・app/services/images.py: 内部リンク（a・svg）・リンク切れ（span）・埋め込み（div・a・p）・
    #   画像（img[width, height]）
    # app/core/dataview.py: div・table・a・ul・li・span・svg
    "a": frozenset({"href", "target"}),
    "img": frozenset({"src", "alt", "width", "height"}),
    "input": frozenset({"type", "checked", "disabled"}),   # タスクのチェックボックスだけ（_is_task_checkbox）
    "h1": _HEADING_ATTRS, "h2": _HEADING_ATTRS, "h3": _HEADING_ATTRS,
    "h4": _HEADING_ATTRS, "h5": _HEADING_ATTRS, "h6": _HEADING_ATTRS,
    "p": _NOTE_ALIGN,
    "div": _NOTE_ALIGN,
    "ol": frozenset({"start"}),
    "td": _NOTE_CELL, "th": _NOTE_CELL,
    "span": _NO_ATTRS, "ul": _NO_ATTRS, "li": _NO_ATTRS, "blockquote": _NO_ATTRS, "hr": _NO_ATTRS, "br": _NO_ATTRS,
    "strong": _NO_ATTRS, "em": _NO_ATTRS, "s": _NO_ATTRS, "mark": _NO_ATTRS, "pre": _NO_ATTRS, "code": _NO_ATTRS,
    "table": _NO_ATTRS, "thead": _NO_ATTRS, "tbody": _NO_ATTRS, "tr": _NO_ATTRS,
    # ---------- ノートでよく使う HTML ----------
    # 折りたたみ・文字の飾りと色・キー・略語・引用・定義リスト・図・表の見出しと列・ルビ・改行の候補
    "details": frozenset({"open"}),
    "font": frozenset({"color", "size", "face"}),
    "col": frozenset({"span"}), "colgroup": frozenset({"span"}),
    "summary": _NO_ATTRS, "u": _NO_ATTRS, "b": _NO_ATTRS, "i": _NO_ATTRS, "small": _NO_ATTRS, "sub": _NO_ATTRS,
    "sup": _NO_ATTRS, "del": _NO_ATTRS, "ins": _NO_ATTRS, "kbd": _NO_ATTRS, "samp": _NO_ATTRS, "var": _NO_ATTRS,
    "abbr": _NO_ATTRS, "cite": _NO_ATTRS, "q": _NO_ATTRS, "dl": _NO_ATTRS, "dt": _NO_ATTRS, "dd": _NO_ATTRS,
    "figure": _NO_ATTRS, "figcaption": _NO_ATTRS, "caption": _NO_ATTRS, "tfoot": _NO_ATTRS, "ruby": _NO_ATTRS,
    "rt": _NO_ATTRS, "rp": _NO_ATTRS, "wbr": _NO_ATTRS,
}

# svg（アプリのアイコン）と、その中で使ってよい部品。グローバルの属性（style など）は付けない
_SVG_ATTRS = frozenset({"xmlns", "width", "height", "viewbox", "fill", "stroke", "stroke-width", "stroke-linecap",
                        "stroke-linejoin", "class"})
_SVG_CHILD_ATTRS: dict[str, frozenset[str]] = {
    "path": frozenset({"d"}),
    "circle": frozenset({"cx", "cy", "r"}),
    "polyline": frozenset({"points"}),
    "line": frozenset({"x1", "y1", "x2", "y2"}),
    "rect": frozenset({"width", "height", "x", "y", "rx"}),
    "polygon": frozenset({"points"}),
}
# html.parser は属性の名前を小文字にする。svg では大文字小文字を区別するので、元の名前に戻して出す。
# アイコンに preserveAspectRatio など大文字を含む属性が増えたら、ここと _SVG_ATTRS（か _SVG_CHILD_ATTRS）の両方に足す
_SVG_ATTR_NAMES = {"viewbox": "viewBox"}

# リンク（href）にしてよい scheme。Markdown の自動リンク（app/core/markdown.py）も、これと同じものだけをリンクにする。
# obsidian: は Obsidian のアプリを開くだけでスクリプトは動かない（ユーザーの決定）
LINK_SCHEMES = frozenset({"http", "https", "mailto", "obsidian"})
# 画像（src）にしてよい scheme
_SRC_SCHEMES = frozenset({"http", "https"})
# 空白・制御文字（ブラウザは URL の前後とタブ・改行を読み飛ばす。判定では全部取り除いて厳しめに見る。style の判定でも使う）
_URL_IGNORED_RE = re.compile(r"[\x00-\x20\x7f-\x9f]+")
# scheme の部分（/ ? # より前に : があれば、その手前が scheme）
_URL_SCHEME_RE = re.compile(r"^([^:/?#]*):")

_ALIGN_VALUES = frozenset({"left", "center", "right", "justify"})
_NEW_TAB_REL = "noopener noreferrer"

# style で使ってよい CSS のプロパティ。ノートとアプリが使うもの（描き比べで確かめた: 表の text-align・カードリンクの
# background-image・改ページの page-break-after・文字の地の background）と、その仲間の色・文字の飾り・寄せ・改ページ。
# ページの部品の上に重ねて見せられるもの（position・z-index・inset・top/left/right/bottom・transform・display）や、
# 大きさ・余白・見え方（width・height・margin・opacity・visibility など）は入れない
_STYLE_PROPERTIES = frozenset({
    # 色・背景（背景の画像の url は http・https だけ。_is_safe_style）
    "color", "background", "background-color", "background-image",
    # 文字の太さ・大きさ・書体・飾り
    "font-weight", "font-style", "font-size", "font-family", "font-variant",
    "text-decoration", "text-decoration-line", "text-decoration-color", "text-decoration-style",
    "text-decoration-thickness",
    # 寄せ
    "text-align", "vertical-align",
    # 改ページ（印刷）
    "page-break-before", "page-break-after", "page-break-inside", "break-before", "break-after", "break-inside",
})
# style で使わせない書き方（空白を詰めて小文字にしてから探す）
_CSS_BANNED = ("expression", "javascript:", "vbscript:", "@import", "-moz-binding", "image-set(", "image(", "src(")
# IE の behavior（scroll-behavior のような名前の一部は見ない）
_CSS_BEHAVIOR_RE = re.compile(r"(?<![a-z-])behavior")
_CSS_URL_RE = re.compile(r"url\(")
_CSS_URL_OK_RE = re.compile(r"""^["']?https?://""")


def sanitize_html(html: str) -> str:
    """描画済みの HTML を、許可したタグと属性とエスケープした文字だけで組み立て直す"""
    return _SafeHtmlRebuilder(html).rebuild()


def _escape(text: str) -> str:
    """文字・属性の値のエスケープ（markdown-it の escapeHtml と同じ & < > " の 4 つ。描画の結果を変えないため）"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _is_safe_url(value: str, schemes: frozenset[str]) -> bool:
    """
    URL が schemes の scheme か、scheme の無い URL（サイト内の /・#・?・相対パス）か

    value はエンティティを戻した後の値（html.parser が戻す）。ブラウザが読み飛ばす空白・制御文字を取り除き、
    大文字小文字を無視して判定する（java\\tscript: や JaVaScRiPt: を通さない）。
    """
    m = _URL_SCHEME_RE.match(_URL_IGNORED_RE.sub("", value).lower())
    return m is None or m.group(1) in schemes


def _clean_style(value: str) -> str | None:
    """
    style の値から、許可したプロパティ（_STYLE_PROPERTIES）の宣言だけを残す。1 つも残らなければ None（属性ごと捨てる）

    危ない書き方（_is_safe_style）があれば属性ごと捨てる。コメント・CSS のエスケープ・閉じていない引用符やかっこも、
    宣言の切れ目をブラウザと読み違えないよう属性ごと捨てる（今のノートとアプリの出力には無い）。
    全部の宣言が残るときは、書いたとおりに出す（描画の結果を変えない）。
    """
    if "/*" in value or "\\" in value or not _is_safe_style(value):
        return None
    declarations = _split_declarations(value)
    if not declarations:
        return None
    kept = [decl for decl in declarations if _is_allowed_declaration(decl)]
    if not kept:
        return None
    return value if len(kept) == len(declarations) else "; ".join(kept)


def _is_safe_style(value: str) -> bool:
    """style の値に、スクリプトを動かす・外のものを読み込む書き方が無いか（url( の中は http/https だけ）"""
    compact = _URL_IGNORED_RE.sub("", value).lower()
    if any(word in compact for word in _CSS_BANNED) or _CSS_BEHAVIOR_RE.search(compact):
        return False
    for m in _CSS_URL_RE.finditer(compact):
        end = compact.find(")", m.end())
        if end < 0 or not _CSS_URL_OK_RE.match(compact[m.end():end]):
            return False
    return True


def _split_declarations(css: str) -> list[str] | None:
    """style の値を宣言ごとに分ける（引用符・かっこの中の ; では分けない）。引用符・かっこが閉じていなければ None"""
    parts: list[str] = []
    current: list[str] = []
    quote = ""
    depth = 0
    for ch in css:
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                return None
            depth -= 1
        elif ch == ";" and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    if quote or depth:
        return None
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def _is_allowed_declaration(declaration: str) -> bool:
    """宣言 1 つ（color: red）が、許可したプロパティで値があるか"""
    name, colon, value = declaration.partition(":")
    return bool(colon) and name.strip().lower() in _STYLE_PROPERTIES and bool(value.strip())


def _is_task_checkbox(attrs: list[tuple[str, str | None]]) -> bool:
    """input がチェックボックスか（タスクのチェックボックスの input だけを残す）"""
    types = [value for name, value in attrs if name == "type"]
    return bool(types) and (types[0] or "").strip().lower() == "checkbox"


class _UnclosedDrop(Exception):
    """中身ごと捨てる要素が、自分の閉じタグより先に外側の要素で閉じられた（開きタグを文字にして読み直す）"""


@dataclass(frozen=True)
class _DropStart:
    """いちばん外側の、中身ごと捨てている要素の開きタグ（閉じなかったときに、ここまで戻って読み直す）"""
    tag_start: int          # 入力の中の、開きタグの始まりの位置
    tag_end: int            # 開きタグの終わりの位置（読み直しはここから）
    out_len: int            # そのときまでに組み立てた出力の数
    open: tuple[str, ...]   # そのときに開いていた要素


class _SafeHtmlRebuilder(HTMLParser):
    """
    html.parser で読んだタグ・文字から、許可したものだけで HTML を組み立て直す

    R4 の閉じタグの元の文字（</Think>）を取るため、HTMLParser.parse_endtag を上書きしている（handle_endtag には
    小文字の名前しか渡らない）。Python の版を上げるときは、tests/test_html_sanitizer.py の
    test_html_parserは閉じタグをparse_endtagの中でhandle_endtagに渡す を必ず流す
    """

    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self._source = source
        self._line_starts: list[int] | None = None   # 入力の各行の始まりの位置（読み直しの位置を求めるときだけ作る）
        self._pass_start = 0                          # いま読んでいる所の、入力の中の始まりの位置
        self._out: list[str] = []
        self._open: list[str] = []                    # 出力した開きタグのうち、まだ閉じていないもの
        self._dropping: list[str] = []                # 中身ごと捨てている要素の入れ子（空なら捨てていない）
        self._drop_start: _DropStart | None = None
        self._endtag_start: int | None = None         # いま読んでいる閉じタグの位置（parse_endtag の中だけ）
        self._endtag_as_text = False                  # いま読んだ閉じタグを、元の文字で出す（R4）

    def rebuild(self) -> str:
        """入力を最後まで読んで、組み立てた HTML を返す（閉じていない要素はここで閉じる）"""
        start = 0
        while True:
            self._read_from(start)
            if self._drop_start is None:
                break
            start = self._unwrap_unclosed_drop()
        while self._open:
            self._out.append(f"</{self._open.pop()}>")
        return "".join(self._out)

    def _read_from(self, start: int) -> None:
        """入力の start から後ろを読む。中身ごと捨てる要素が閉じなかったら、_drop_start を残して戻る"""
        self.reset()
        self._pass_start = start
        self._dropping = []
        self._endtag_start = None
        self._endtag_as_text = False
        try:
            self.feed(self._source[start:])
            self.close()
        except _UnclosedDrop:
            pass

    def _unwrap_unclosed_drop(self) -> int:
        """閉じなかった中身ごと捨てる要素の開きタグを文字にして、読み直す位置（開きタグの直後）を返す"""
        drop = self._drop_start
        self._drop_start = None
        del self._out[drop.out_len:]
        self._open = list(drop.open)
        self._out.append(_escape(self._source[drop.tag_start:drop.tag_end]))
        return drop.tag_end

    def _source_index(self) -> int:
        """いま読んでいるタグの始まりの、入力の中の位置（getpos の行・列から求める）"""
        line, col = self.getpos()
        if line == 1:
            return self._pass_start + col
        if self._line_starts is None:
            self._line_starts = [0] + [m.end() for m in re.finditer("\n", self._source)]
        first_line = bisect.bisect_right(self._line_starts, self._pass_start) - 1
        return self._line_starts[first_line + line - 1] + col

    def _begin_drop(self, tag: str) -> None:
        """中身ごと捨て始める。いちばん外側なら、閉じなかったときに戻る場所を覚える"""
        if not self._dropping:
            tag_start = self._source_index()
            self._drop_start = _DropStart(tag_start, tag_start + len(self.get_starttag_text() or ""),
                                          len(self._out), tuple(self._open))
        self._dropping.append(tag)

    # ---------- 開きタグ ----------

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, self_closing=True)

    def _start(self, tag: str, attrs: list[tuple[str, str | None]], self_closing: bool) -> None:
        opens_content = not self_closing and tag not in _VOID_ELEMENTS
        if self._dropping:
            if opens_content and tag in _DROP_WITH_CONTENT:
                self._dropping.append(tag)
            return
        if "svg" in self._open:
            if tag in _SVG_CHILD_ATTRS:
                self._emit_start(tag, self._svg_attrs(attrs, _SVG_CHILD_ATTRS[tag]), self_closing, foreign=True)
            elif opens_content:
                # svg の中のほかの要素（script・foreignObject・a・animate・use など）は中身ごと捨てる
                self._begin_drop(tag)
            return
        if tag in _DROP_WITH_CONTENT:
            if opens_content:
                self._begin_drop(tag)
            return
        if tag == "svg":
            self._emit_start(tag, self._svg_attrs(attrs, _SVG_ATTRS), self_closing, foreign=True)
        elif tag in _ALLOWED_ATTRS:
            if tag == "input" and not _is_task_checkbox(attrs):
                return
            self._emit_start(tag, self._html_attrs(tag, attrs), self_closing)
        elif tag not in _HTML_ELEMENTS:
            # R4: HTML に無いタグは、元のタグの文字のまま見せる
            self._out.append(_escape(self.get_starttag_text() or ""))
        # HTML にはあるが許可していないタグは、タグだけ外す（中身は続けて読む）

    def _emit_start(self, tag: str, attrs: list[str], self_closing: bool, foreign: bool = False) -> None:
        """開きタグを出す。foreign は svg とその部品（/> で閉じた要素になる）"""
        attr_text = "".join(f" {attr}" for attr in attrs)
        if tag in _VOID_ELEMENTS:
            # <br /> と書いてあれば <br /> のまま（markdown-it の出力を変えない）
            self._out.append(f"<{tag}{attr_text}{' /' if self_closing else ''}>")
        elif self_closing and foreign:
            # svg の部品の <path .../> は、svg の中では閉じた要素になる
            self._out.append(f"<{tag}{attr_text}/>")
        else:
            # HTML の <div/> はブラウザでは開きタグなので、閉じタグを補って中身を持たせない
            self._out.append(f"<{tag}{attr_text}>")
            if self_closing:
                self._out.append(f"</{tag}>")
            else:
                self._open.append(tag)

    def _html_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> list[str]:
        allowed = _GLOBAL_ATTRS | _ALLOWED_ATTRS[tag]
        out: list[str] = []
        for name, value in _first_of_each(attrs):
            if name not in allowed:
                continue
            if name in ("href", "src"):
                schemes = LINK_SCHEMES if name == "href" else _SRC_SCHEMES
                if value is None or not _is_safe_url(value, schemes):
                    continue
            elif name == "style":
                value = _clean_style(value) if value is not None else None
                if value is None:
                    continue
            elif name == "align":
                if (value or "").strip().lower() not in _ALIGN_VALUES:
                    continue
            elif name == "target":
                # 新しいタブ（_blank）だけ。開いた先のページから元のページを操作させない
                if (value or "").strip().lower() == "_blank":
                    out.append('target="_blank"')
                    out.append(f'rel="{_NEW_TAB_REL}"')
                continue
            out.append(_attr(name, value))
        return out

    def _svg_attrs(self, attrs: list[tuple[str, str | None]], allowed: frozenset[str]) -> list[str]:
        return [_attr(_SVG_ATTR_NAMES.get(name, name), value)
                for name, value in _first_of_each(attrs) if name in allowed]

    # ---------- 閉じタグ ----------

    def parse_endtag(self, i):
        # 閉じタグの元の文字（R4 で文字として出す）を取るため、読んだ範囲を覚えておく。
        # handle_endtag には名前（小文字）しか渡らないので、</T> を </t> にしないよう元の文字を使う
        self._endtag_start = i
        try:
            end = super().parse_endtag(i)
        finally:
            self._endtag_start = None
        if self._endtag_as_text:
            self._endtag_as_text = False
            if end > i:
                self._out.append(_escape(self.rawdata[i:end]))
        return end

    def handle_endtag(self, tag):
        if not self._end(tag):
            return
        if self._endtag_start is None:
            # 保険: html.parser の作りが変わり、parse_endtag の外から呼ばれたときは、名前（小文字）で出す
            self._out.append(_escape(f"</{tag}>"))
        else:
            self._endtag_as_text = True   # parse_endtag が元の文字で出す

    def _end(self, tag: str) -> bool:
        """閉じタグを処理する。R4 で元の文字のまま見せる閉じタグなら True"""
        if self._dropping:
            if tag in self._dropping:
                # 入れ子の内側から、この要素までを閉じる
                while self._dropping.pop() != tag:
                    pass
                if not self._dropping:
                    self._drop_start = None   # 自分の閉じタグで閉じたので、中身ごと捨ててよい
                return False
            if tag in self._open:
                # 自分の閉じタグより先に外側の要素が閉じた。開きタグを文字にして読み直す（rebuild）
                raise _UnclosedDrop
            return False
        if tag in self._open:
            while True:
                top = self._open.pop()
                self._out.append(f"</{top}>")
                if top == tag:
                    return False
        if tag in _HTML_ELEMENTS or ("svg" in self._open and tag in _SVG_CHILD_ATTRS):
            # 開いていない閉じタグ（</div></article> など）はブラウザでも意味が無いので捨てる
            return False
        # R4: HTML に無いタグの閉じタグ
        return True

    # ---------- 文字・そのほか ----------

    def handle_data(self, data):
        if not self._dropping:
            self._out.append(_escape(data))

    def handle_comment(self, data):
        pass

    def handle_decl(self, decl):
        pass

    def handle_pi(self, data):
        pass

    def unknown_decl(self, data):
        pass


def _first_of_each(attrs: list[tuple[str, str | None]]):
    """同じ名前の属性は最初の 1 つだけ（ブラウザと同じ）"""
    seen: set[str] = set()
    for name, value in attrs:
        if name not in seen:
            seen.add(name)
            yield name, value


def _attr(name: str, value: str | None) -> str:
    """属性 1 つの文字。値の無い属性（checked・open など）は名前だけ"""
    return name if value is None else f'{name}="{_escape(value)}"'
