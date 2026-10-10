"""ショートカットの定義（app/shortcuts.py）の単体テスト（F-9）

- グループとキーが重複しない
- ? でショートカット一覧を開く行がある
- 管理者だけのグループは管理者にだけ返す
- チートシートは、いまの画面だけのグループ → どの画面でも → そのほか の順に並べる
"""
from app.shortcuts import (
    ALL_PAGE_IDS, FOCUS_PLACES, PAGES, SHORTCUT_GROUPS, Shortcut, find_page, find_shortcut, group, groups_for_page,
    visible_groups,
)


def test_グループのidと見出しは重複しない():
    ids = [group.id for group in SHORTCUT_GROUPS]
    labels = [group.label for group in SHORTCUT_GROUPS]
    assert len(ids) == len(set(ids))
    assert len(labels) == len(set(labels))


def test_同じグループの中でキーは重複しない():
    for group in SHORTCUT_GROUPS:
        chords = [chord for shortcut in group.shortcuts for chord in shortcut.keys]
        assert len(chords) == len(set(chords)), group.id


def test_どのショートカットにもキーと説明がある():
    for group in SHORTCUT_GROUPS:
        assert group.shortcuts, group.id
        assert group.contexts, group.id
        for shortcut in group.shortcuts:
            assert shortcut.keys and all(shortcut.keys), shortcut
            assert shortcut.description and shortcut.short, shortcut


def test_どの画面でもハテナでショートカット一覧を開ける():
    global_group = group("global")
    assert global_group.contexts == ALL_PAGE_IDS
    assert any(s.keys == (("?",),) and s.description == "ショートカット一覧を開く" for s in global_group.shortcuts)


def test_管理者だけのグループは管理者にだけ返す():
    assert visible_groups(True) == SHORTCUT_GROUPS
    public_ids = [group.id for group in visible_groups(False)]
    assert "editor" not in public_ids
    assert public_ids == [group.id for group in SHORTCUT_GROUPS if not group.admin_only]
    assert group("editor").admin_only


def test_bodyのクラスから画面を引く():
    assert find_page("page-editor").id == "editor"
    assert find_page("readable-width graph-page").id == "graph"
    assert find_page("") is None
    assert len({page.body_class for page in PAGES}) == len(PAGES)


def test_チートシートはいまの画面だけのグループを先頭に並べる():
    ids = [group.id for group in groups_for_page(find_page("page-editor"), True)]
    assert ids[:2] == ["editor", "global"]
    assert sorted(ids) == sorted(group.id for group in SHORTCUT_GROUPS)


def test_チートシートは画面が分からなければ定義の順():
    assert groups_for_page(None, False) == visible_groups(False)
    assert groups_for_page(find_page("page-view"), False)[0].id == "global"


def test_説明文の角かっこはキーの見た目にしてほかはエスケープする():
    shortcut = Shortcut((("↑",),), "先頭で [↑] を押す <b>&", "移動")
    assert str(shortcut.description_html) == "先頭で <kbd>↑</kbd> を押す &lt;b&gt;&amp;"


def test_どのグループも画面かフォーカスの場所のどれかで使える():
    known = ALL_PAGE_IDS | FOCUS_PLACES
    for g in SHORTCUT_GROUPS:
        assert g.contexts <= known, g.id
    # フォーカスの場所ごとに、その場所のグループがちょうど1つある（下の段・チートシートの先頭に出すもの）
    for place in FOCUS_PLACES:
        assert len([g for g in SHORTCUT_GROUPS if place in g.contexts]) == 1, place


def test_キーでショートカットを引く():
    assert find_shortcut("global", ("Esc",)).short == "閉じる"
