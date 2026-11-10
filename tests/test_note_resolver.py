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
