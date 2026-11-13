"""NoteResolver（app/core/note_resolver.py）の契約テスト

F-11: Vault のルートから書いたパス（[[notes/…]]）を引ける。
B-16: 同名ノートがあっても、解決先が更新日時や並び順で入れ替わらない。
"""
import itertools

from app.core.note_resolver import NoteResolver

ENTRIES = [
    ("coding-tips/layering.md", "notes/coding-tips/layering.md"),
    ("CDM-3020 広告ソケット通信設定.md", "notes/CDM-3020 広告ソケット通信設定.md"),
    ("llm-wiki/wiki/dev-tech/CDM-3020 広告ソケット通信設定.md", "llm-wiki/wiki/dev-tech/CDM-3020 広告ソケット通信設定.md"),
    ("llm-wiki/wiki/dev-tech/other.md", "llm-wiki/wiki/dev-tech/other.md"),
    ("llm-wiki/wiki/qa-test/x.md", "llm-wiki/wiki/qa-test/x.md"),
    ("llm-wiki/CLAUDE.md", "llm-wiki/CLAUDE.md"),
    ("会議/定例.md", None),
]


def test_ファイル名で引ける_末尾の_md_は無視する():
    r = NoteResolver(ENTRIES)
    assert r.resolve("layering") == "coding-tips/layering.md"
    assert r.resolve("layering.md") == "coding-tips/layering.md"
    assert r.resolve("定例") == "会議/定例.md"
    assert r.resolve("無い") is None
    assert r.resolve("") is None


def test_パス指定はビューアのパスでもVaultのパスでも引ける():
    r = NoteResolver(ENTRIES)
    assert r.resolve("notes/coding-tips/layering") == "coding-tips/layering.md"
    assert r.resolve("coding-tips/layering") == "coding-tips/layering.md"
    assert r.resolve("/coding-tips/layering") == "coding-tips/layering.md"
    assert r.resolve("llm-wiki/CLAUDE") == "llm-wiki/CLAUDE.md"
    assert r.resolve("会議/定例") == "会議/定例.md"


def test_パス指定は完全一致が無ければ段の区切りで末尾一致する():
    r = NoteResolver(ENTRIES)
    assert r.resolve("wiki/qa-test/x") == "llm-wiki/wiki/qa-test/x.md"
    # 段の途中からは一致させない
    assert r.resolve("ki/qa-test/x") is None


def test_同名は_リンク元と同じフォルダ_段数の少ない方_辞書順の順で選ぶ():
    r = NoteResolver(ENTRIES)
    name = "CDM-3020 広告ソケット通信設定"
    assert r.resolve(name) == "CDM-3020 広告ソケット通信設定.md"
    assert r.resolve(name, "llm-wiki/wiki/dev-tech/other.md") == "llm-wiki/wiki/dev-tech/CDM-3020 広告ソケット通信設定.md"
    assert r.resolve(name, "会議/定例.md") == "CDM-3020 広告ソケット通信設定.md"

    same_depth = NoteResolver([("b/x.md", None), ("a/x.md", None)])
    assert same_depth.resolve("x") == "a/x.md"


def test_結果はentriesの並び順に依存しない():
    for perm in itertools.permutations(ENTRIES[:4]):
        r = NoteResolver(perm)
        assert r.resolve("CDM-3020 広告ソケット通信設定") == "CDM-3020 広告ソケット通信設定.md"
        assert r.resolve("other", "x.md") == "llm-wiki/wiki/dev-tech/other.md"


def test_has_stem():
    r = NoteResolver(ENTRIES)
    assert r.has_stem("layering") and r.has_stem("定例")
    assert not r.has_stem("無い")


def test_大文字小文字は区別する():
    assert NoteResolver(ENTRIES).resolve("Layering") is None


# ---------- X-2: frontmatter の別名（aliases） ----------

ALIAS_ENTRIES = [("会議/定例.md", None), ("メモ/下書き.md", None), ("a/同名.md", None), ("b/同名.md", None)]


def test_別名で引ける():
    r = NoteResolver(ALIAS_ENTRIES, [("週次", "会議/定例.md")])
    assert r.resolve("週次") == "会議/定例.md"
    assert r.resolve("週次.md") == "会議/定例.md"
    assert r.resolve("/週次") == "会議/定例.md"


def test_ファイル名が別名より優先される():
    r = NoteResolver(ALIAS_ENTRIES, [("下書き", "会議/定例.md")])
    assert r.resolve("下書き") == "メモ/下書き.md"


def test_パス指定でも見つからなければ別名を引く():
    r = NoteResolver(ALIAS_ENTRIES, [("x/週次", "会議/定例.md")])
    assert r.resolve("x/週次") == "会議/定例.md"
    # パスとして見つかるものは別名より優先する
    r = NoteResolver(ALIAS_ENTRIES, [("メモ/下書き", "会議/定例.md")])
    assert r.resolve("メモ/下書き") == "メモ/下書き.md"


def test_別名が複数のノートにあれば同名ノートと同じ選び方で並び順に依存しない():
    aliases = [("共通", "z/深い/b.md"), ("共通", "z/a.md"), ("共通", "y/a.md"), ("共通", "w/x/c.md")]
    entries = [(p, None) for _, p in aliases]
    expected_by_source = {"": "y/a.md", "z/深い/x.md": "z/深い/b.md", "w/x/q.md": "w/x/c.md"}
    for perm in itertools.permutations(aliases):
        r = NoteResolver(entries, perm)
        for source, expected in expected_by_source.items():
            assert r.resolve("共通", source) == expected


def test_has_stemは別名を見ない():
    r = NoteResolver(ALIAS_ENTRIES, [("週次", "会議/定例.md")])
    assert r.has_stem("定例") and not r.has_stem("週次")


def test_別名が無いときの挙動は今までどおり():
    r = NoteResolver(ALIAS_ENTRIES)
    assert r.resolve("週次") is None
