"""同期元の対応表（app/core/content_sources.py）の契約テスト

- 元フォルダ（置き場所 ""）と、追加の同期元（置き場所 = ビューア内の 1 段のフォルダ名）を持つ
- 使えない追加の同期元は invalid に入れ、extras には入れない
- ビューアのパス → 同期元・同期元側のパス・Vault のルートからのパスを引く
- 運ばないもの（ドットで始まる段・exclude）は同期元側のパスにしない
"""
from pathlib import Path

import pytest

from app.config import PROTECTED_ITEMS
from app.core.content_sources import ContentSource, ContentSources, check_dest, normalize_exclude
from app.models.sync import ExtraSource, SyncConfig


@pytest.fixture
def vault(tmp_path):
    """Vault（.obsidian あり）の下に notes と llm-wiki がある"""
    root = tmp_path / "vault"
    (root / ".obsidian").mkdir(parents=True)
    for d in ("notes/会議", "llm-wiki/wiki", "llm-wiki/raw"):
        (root / d).mkdir(parents=True)
    return root


def _config(vault: Path, *extras: ExtraSource) -> SyncConfig:
    return SyncConfig(content_src=str(vault / "notes"), extra_sources=list(extras))


def _wiki(vault: Path, **kwargs) -> ExtraSource:
    return ExtraSource(src=str(vault / "llm-wiki"), dest="llm-wiki", **kwargs)


# ---------- ContentSource ----------

@pytest.mark.parametrize("rel, expected", [
    ("a.md", False),
    ("会議/a.md", False),
    (".obsidian/app.json", True),
    ("会議/.hidden/a.md", True),
    ("会議/.a.md", True),
    ("raw", True),
    ("raw/a.pdf", True),
    ("rawdata/a.md", False),     # 名前の前方一致では除かない
    ("wiki/raw", False),
])
def test_運ばないものの判定(rel, expected):
    source = ContentSource(src=Path("/x"), dest="llm-wiki", exclude=("raw",))
    assert source.is_excluded(rel) is expected


def test_除外の指定は階層を含められる():
    source = ContentSource(src=Path("/x"), dest="d", exclude=("wiki/private",))
    assert source.is_excluded("wiki/private/a.md")
    assert not source.is_excluded("wiki/public/a.md")


def test_ビューアのパスは置き場所を前に付ける():
    assert ContentSource(src=Path("/x")).view_path("a/b.md") == "a/b.md"
    assert ContentSource(src=Path("/x"), dest="llm-wiki").view_path("a/b.md") == "llm-wiki/a/b.md"


def test_除外の指定をそろえる():
    assert normalize_exclude([" raw/ ", "\\wiki\\private\\", "", "  ", "/", "raw"]) == ("raw", "wiki/private")


# ---------- 置き場所の検査 ----------

@pytest.mark.parametrize("dest", ["llm-wiki", "wiki", "日本語"])
def test_使える置き場所(dest):
    assert check_dest(dest) == ""


@pytest.mark.parametrize("dest", ["", " ", "a/b", "a\\b", ".hidden", "a:b", "a*", "a?", 'a"b', "a<b", "a>b", "a|b", " x",
                                  *PROTECTED_ITEMS])
def test_使えない置き場所(dest):
    assert check_dest(dest) != ""


# ---------- 設定から作る ----------

def test_元フォルダは置き場所が空():
    sources = ContentSources.from_config(SyncConfig(content_src="/v/notes"))
    assert sources.origin == ContentSource(src=Path("/v/notes"), dest="")
    assert sources.extras == () and sources.invalid == ()


def test_元フォルダが空なら元フォルダは無い():
    assert ContentSources.from_config(SyncConfig()).origin is None


def test_追加の同期元を持つ(vault):
    sources = ContentSources.from_config(_config(vault, _wiki(vault, exclude=[" raw/ ", ""])))
    assert [(e.dest, e.exclude) for e in sources.extras] == [("llm-wiki", ("raw",))]


def test_使えない追加の同期元はinvalidに入れる(vault):
    extras = [
        ExtraSource(src="", dest="a"),                          # src が空
        ExtraSource(src="/x", dest="a/b"),                      # 2 段
        ExtraSource(src="/x", dest=".git"),                     # ドット始まり
        ExtraSource(src="/x", dest="samples"),                  # 保護対象と同名
        _wiki(vault),                                           # これは使える
        ExtraSource(src=str(vault), dest="llm-wiki"),           # 重複（あとのほうが使えない）
    ]
    sources = ContentSources.from_config(_config(vault, *extras))
    assert [e.dest for e in sources.extras] == ["llm-wiki"]
    assert [e.src for e, _ in sources.invalid] == ["", "/x", "/x", "/x", str(vault)]
    assert all(reason for _, reason in sources.invalid)


def test_invalidは引き先にならない(vault):
    sources = ContentSources.from_config(_config(vault, ExtraSource(src=str(vault / "llm-wiki"), dest="a/b")))
    assert sources.source_of("a/b/x.md") == sources.origin


# ---------- 引く ----------

@pytest.fixture
def sources(vault):
    return ContentSources.from_config(_config(vault, _wiki(vault, exclude=["raw"])))


def test_追加の同期元の置き場所なら追加の同期元(sources):
    assert sources.source_of("llm-wiki/wiki/x.md").dest == "llm-wiki"


def test_それ以外は元フォルダ(sources):
    assert sources.source_of("会議/a.md") is sources.origin


def test_保護対象は同期元が無い(sources):
    assert sources.source_of("samples/a.md") is None
    assert sources.source_of("demo.md") is None


def test_元フォルダが無ければ追加の同期元以外はNone(vault):
    sources = ContentSources.from_config(SyncConfig(extra_sources=[_wiki(vault)]))
    assert sources.source_of("a.md") is None
    assert sources.source_of("llm-wiki/a.md").dest == "llm-wiki"


def test_同期元側のパス(sources, vault):
    assert sources.host_path("llm-wiki/wiki/x.md") == (vault / "llm-wiki" / "wiki" / "x.md").resolve()
    assert sources.host_path("会議/a.md") == (vault / "notes" / "会議" / "a.md").resolve()


def test_存在は見ない(sources):
    assert sources.host_path("会議/無い.md") is not None


@pytest.mark.parametrize("path", [
    "samples/a.md",
    "llm-wiki",                       # 置き場所そのもの
    "llm-wiki/../notes/a.md",         # 外へ出る
    "llm-wiki/raw/a.md",              # exclude
    "llm-wiki/.obsidian/a.json",      # ドット
    "../x.md",
    "会議/../../x.md",
])
def test_同期元側のパスにならないもの(sources, path):
    assert sources.host_path(path) is None


def test_外を指すシンボリックリンクは同期元側のパスにならない(sources, vault, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = vault / "llm-wiki" / "wiki" / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("シンボリックリンクを作れない環境")
    assert sources.host_path("llm-wiki/wiki/link/a.md") is None


# ---------- Vault のルートからのパス ----------

def test_Vaultのルートからのパス(sources):
    assert sources.vault_path("llm-wiki/wiki/x.md") == "llm-wiki/wiki/x.md"
    assert sources.vault_path("会議/a.md") == "notes/会議/a.md"


def test_Vaultのルートが同期元自身にあるとき(tmp_path):
    (tmp_path / "v" / ".obsidian").mkdir(parents=True)
    sources = ContentSources.from_config(SyncConfig(content_src=str(tmp_path / "v")))
    assert sources.vault_path("a/b.md") == "a/b.md"


def test_Vaultのルートが無ければNone(tmp_path):
    (tmp_path / "notes").mkdir()
    sources = ContentSources.from_config(SyncConfig(content_src=str(tmp_path / "notes")))
    # tmp_path の親に .obsidian が無い前提（あればその親がルートになる）
    if sources.origin.vault_root is None:
        assert sources.vault_path("a.md") is None


def test_同期元が無いパスのVaultパスはNone(sources):
    assert sources.vault_path("samples/a.md") is None
    assert sources.vault_path("llm-wiki/raw/a.md") is None


def test_Vaultのルートは作るときに1回だけ探す(vault):
    sources = ContentSources.from_config(_config(vault, _wiki(vault)))
    (vault / ".obsidian").rmdir()
    assert sources.vault_path("llm-wiki/wiki/x.md") == "llm-wiki/wiki/x.md"


# ---------- 同期で守る名前・ぶつかり ----------

def test_元フォルダは追加の同期元の置き場所も守る(sources):
    assert sources.protected_for(sources.origin) == PROTECTED_ITEMS + ["llm-wiki"]


def test_追加の同期元は何も守らない(sources):
    assert sources.protected_for(sources.extras[0]) == []


def test_元フォルダの直下に同じ名前があればぶつかる(vault):
    (vault / "notes" / "llm-wiki").mkdir()
    sources = ContentSources.from_config(_config(vault, _wiki(vault)))
    assert [c.dest for c in sources.conflicts()] == ["llm-wiki"]


def test_ぶつかりが無ければ空(sources):
    assert sources.conflicts() == []


def test_対応表は読み取り専用(sources):
    with pytest.raises(Exception):
        sources.origin = None


def test_使えない追加の同期元でも置き場所の形が正しければ守る(vault):
    extras = [ExtraSource(src="", dest="empty-src"), _wiki(vault), ExtraSource(src=str(vault), dest="llm-wiki"),
              ExtraSource(src="/x", dest="a/b")]
    sources = ContentSources.from_config(_config(vault, *extras))
    protected = sources.protected_for(sources.origin)
    assert protected == PROTECTED_ITEMS + ["llm-wiki", "empty-src"]   # 重なった名前は 1 回、形の悪い a/b は入れない


def test_行ごとの問題を返す(vault):
    from app.core.content_sources import extra_source_problems
    (vault / "notes" / "taken").mkdir()
    rows = [ExtraSource(src=str(vault / "llm-wiki"), dest="ok"), ExtraSource(src="", dest="ok"),
            ExtraSource(src=str(vault / "llm-wiki"), dest="ok"), ExtraSource(src=str(vault / "none"), dest="taken")]
    assert [(i, f) for i, f, _ in extra_source_problems(rows)] == [(1, "src"), (1, "dest"), (2, "dest")]
    found = extra_source_problems(rows, str(vault / "notes"), check_filesystem=True)
    assert [(i, f) for i, f, _ in found] == [(1, "src"), (1, "dest"), (2, "dest"), (3, "src"), (3, "dest")]


def test_vault_pathはファイルシステムに触れない(sources, monkeypatch):
    def fail(self, *args, **kwargs):
        raise AssertionError("Path.resolve を呼んではいけない")

    monkeypatch.setattr(Path, "resolve", fail)
    assert sources.vault_path("llm-wiki/wiki/x.md") == "llm-wiki/wiki/x.md"
    assert sources.vault_path("会議/a.md") == "notes/会議/a.md"


@pytest.mark.parametrize("path", ["llm-wiki/../x.md", "../x.md", "会議/../../x.md", "/etc/passwd", "llm-wiki/", "llm-wiki",
                                  "会議//a.md", "会議/./a.md", "samples/a.md", "llm-wiki/raw/a.md", "llm-wiki/.git/a.md"])
def test_vault_pathにならないパス(sources, path):
    assert sources.vault_path(path) is None
