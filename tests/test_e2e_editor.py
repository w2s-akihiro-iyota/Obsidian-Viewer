"""エディタの E2E（B-30・X-14・X-15。仕組みは conftest.py の e2e。768px をまたぐ動きは test_e2e_responsive.py）

- プレビューの数式: ドル記号の数式（Markdown の描画の dollarmath が作る .math.inline・.math.block）も、
  記事ページと同じく KaTeX で描く（math.js の renderMathIn を記事ページと共有する。B-30）
- 境目のつかめる範囲: 見た目の線（4px）はそのままで、プレビューの側へ広げた範囲でもつかめる。
  入力欄の側には広げない（入力欄のスクロールバーにかぶる）（X-14）
- 境目のキーボード: 区切り（role="separator"）として読み上げ、今の幅（aria-valuenow。入力欄の幅の %）を持つ。
  クリックかフォーカスで選び、[←] [→] で 5% ずつ、[Home] [End] でいちばん狭く（20%）・広く（80%）する。
  選んでいるときに ? を押すと、一覧の先頭に「エディタの境目」が出る。スマホの幅（縦並び）では選べない（X-15）

プレビューは POST /api/editor/preview（e2e はプレビューだけサーバーに届かせる）
"""
import re

from conftest import E2E_EDITOR_RESIZER, E2E_PHONE, E2E_SHORTCUT_SHEET, import_playwright

expect = import_playwright().expect

TEXTAREA = "#editor-textarea"
PREVIEW = "#editor-preview"
INPUT_PANE = ".editor-input-pane"
PANES = ".editor-panes"
SEPARATOR_LABEL = "編集とプレビューの境目"
RATIO_MIN, RATIO_MAX, RATIO_STEP = 20, 80, 5
HIT_OUTSIDE_LINE = 12           # 見た目の線の右端から、この px 先（プレビューの側）でもつかめる
RESIZER_GROUP_TITLE = "エディタの境目（管理者のみ）"
SHEET_FIRST_GROUP_TITLE = f"{E2E_SHORTCUT_SHEET} .shortcut-sheet-group:not([hidden]) .shortcut-sheet-sec"


def _input_ratio(page) -> float:
    """入力欄の幅（枠に対する %）"""
    return page.evaluate(f"""() => document.querySelector('{INPUT_PANE}').getBoundingClientRect().width
        / document.querySelector('{PANES}').getBoundingClientRect().width * 100""")


def _expect_ratio(page, resizer, ratio: int) -> None:
    expect(resizer).to_have_attribute("aria-valuenow", str(ratio))
    # 境目の幅のぶん、入力欄の幅は少しずれる
    e2e_ratio = _input_ratio(page)
    assert abs(e2e_ratio - ratio) < 1.5, f"入力欄の幅 {e2e_ratio:.1f}% が aria-valuenow {ratio}% と合わない"


# ---------- プレビューの数式（B-30） ----------

def test_プレビューでドル記号の数式もKaTeXで描く(e2e):
    page = e2e.open_path("/editor")
    page.locator(TEXTAREA).fill("インライン $E=mc^2$ の式\n\n$$\n\\int_0^1 x\\,dx\n$$\n")
    expect(page.locator(f"{PREVIEW} .math.inline .katex")).to_have_count(1)
    expect(page.locator(f"{PREVIEW} .math.block .katex-display")).to_have_count(1)


# ---------- 境目のつかめる範囲（X-14） ----------

def test_境目は見た目の線の外のプレビュー側でもつかめて入力欄の側には広げない(e2e):
    page = e2e.open_path("/editor")
    resizer = page.locator(E2E_EDITOR_RESIZER)
    box = resizer.bounding_box()
    y = box["y"] + box["height"] / 2
    hit = page.evaluate("([x, y]) => document.elementFromPoint(x, y)?.closest('#editor-resizer') !== null",
                        [box["x"] + box["width"] + HIT_OUTSIDE_LINE, y])
    assert hit, f"見た目の線の {HIT_OUTSIDE_LINE}px 右（プレビューの側）でつかめない"
    left = page.evaluate("([x, y]) => document.elementFromPoint(x, y)?.id", [box["x"] - 3, y])
    assert left == TEXTAREA.lstrip("#"), f"入力欄の側まで境目が広がっている（{left}）"

    # 広げた範囲からドラッグしても、つかんだ所が境目についてくる（入力欄が、動かした分だけ広がる）
    before = page.locator(INPUT_PANE).bounding_box()["width"]
    page.mouse.move(box["x"] + box["width"] + HIT_OUTSIDE_LINE, y)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] + HIT_OUTSIDE_LINE + 100, y, steps=5)
    page.mouse.up()
    grown = page.locator(INPUT_PANE).bounding_box()["width"] - before
    assert abs(grown - 100) < 8, f"100px 動かしたのに入力欄が {grown:.0f}px 広がった（つかんだ所がずれる）"


# ---------- 境目のキーボード（X-15） ----------

def test_境目は区切りとして読み上げられ今の幅を持つ(e2e):
    page = e2e.open_path("/editor")
    resizer = page.locator(E2E_EDITOR_RESIZER)
    expect(resizer).to_have_attribute("role", "separator")
    expect(resizer).to_have_attribute("aria-orientation", "vertical")
    expect(resizer).to_have_attribute("aria-label", SEPARATOR_LABEL)
    expect(resizer).to_have_attribute("aria-valuemin", str(RATIO_MIN))
    expect(resizer).to_have_attribute("aria-valuemax", str(RATIO_MAX))
    expect(resizer).to_have_attribute("tabindex", "0")
    expect(resizer).to_have_attribute("title", re.compile("ドラッグ"))
    _expect_ratio(page, resizer, round(_input_ratio(page)))


def test_境目をクリックして矢印とHomeEndで幅を変える(e2e):
    page = e2e.open_path("/editor")
    resizer = page.locator(E2E_EDITOR_RESIZER)
    resizer.click()
    expect(resizer).to_be_focused()
    start = int(resizer.get_attribute("aria-valuenow"))
    page.keyboard.press("ArrowRight")
    _expect_ratio(page, resizer, start + RATIO_STEP)
    page.keyboard.press("ArrowLeft")
    page.keyboard.press("ArrowLeft")
    _expect_ratio(page, resizer, start - RATIO_STEP)
    page.keyboard.press("Home")
    _expect_ratio(page, resizer, RATIO_MIN)
    page.keyboard.press("ArrowLeft")     # いちばん狭いところからは狭くならない
    _expect_ratio(page, resizer, RATIO_MIN)
    page.keyboard.press("End")
    _expect_ratio(page, resizer, RATIO_MAX)


def test_境目を選んでいるときのショートカット一覧は境目のグループが先頭(e2e):
    page = e2e.open_path("/editor")
    page.locator(E2E_EDITOR_RESIZER).focus()
    page.keyboard.press("Shift+Slash")
    expect(page.locator(E2E_SHORTCUT_SHEET)).to_have_class(re.compile(r"\bactive\b"))
    expect(page.locator(SHEET_FIRST_GROUP_TITLE).first).to_have_text(RESIZER_GROUP_TITLE)


def test_スマホの幅では境目を選べない(e2e):
    page = e2e.open_path("/editor", width=E2E_PHONE)
    resizer = page.locator(E2E_EDITOR_RESIZER)
    expect(resizer).to_have_attribute("tabindex", "-1")
    expect(resizer).to_have_attribute("aria-hidden", "true")
