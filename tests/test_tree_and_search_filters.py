"""ファイルツリー（F-1）とクイックスイッチャーの絞り込み（F-2）の契約テスト

実行: docker exec -w /app obsidian-viewer-app python -m pytest tests/test_tree_and_search_filters.py -q -p no:cacheprovider（手順は CLAUDE.md の Testing）
"""
import pytest

from app.core.indexing import get_file_tree
from app.core.search import SearchIndex, parse_search_query


# --- ファイルツリー ---

@pytest.fixture
def vault(tmp_path):
    def write(rel, publish):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"---\npublish: {str(publish).lower()}\ntitle: タイトル違い\n---\n本文", encoding="utf-8")

    write("公開/b.md", True)
    write("公開/A.md", True)
    write("公開/下書き.md", False)
    write("非公開だけ/秘密.md", False)
    write("非公開だけ/深い/秘密2.md", False)
    write("直下.md", True)
    (tmp_path / "空フォルダ").mkdir()
    return tmp_path


def _names(nodes):
    return [n["name"] for n in nodes]


def test_public_tree_hides_folders_with_only_private_notes(vault):
    tree = get_file_tree(vault, vault, published_only=True)
    assert _names(tree) == ["公開", "直下.md"]
    assert _names(tree[0]["children"]) == ["A.md", "b.md"]


def test_admin_tree_has_all_notes_with_published_flag(vault):
    tree = get_file_tree(vault, vault, published_only=False)
    # 空のフォルダは出さない。フォルダが先、名前順（大文字小文字は区別しない）
    assert _names(tree) == ["公開", "非公開だけ", "直下.md"]
    public_folder = tree[0]
    assert public_folder["path"] == "公開"
    assert [(n["name"], n["published"]) for n in public_folder["children"]] == [
        ("A.md", True), ("b.md", True), ("下書き.md", False)]
    nested = tree[1]["children"][0]
    assert nested["type"] == "directory" and nested["path"] == "非公開だけ/深い"


# --- 検索の絞り込み ---

def test_parse_search_query_splits_filters_and_text():
    q = parse_search_query('docker tag:#会議 path:"テスト 仕様" 手順')
    assert q.text == "docker 手順"
    assert q.tags == ["会議"]
    assert q.paths == ["テスト 仕様"]


def test_parse_search_query_without_filters():
    q = parse_search_query("  tagline  path ")
    assert q.text == "tagline path"
    assert not q.has_filters


@pytest.mark.parametrize("query, path, tags, expected", [
    ("tag:会議", "a.md", ["会議"], True),
    ("tag:会議", "a.md", ["会議/定例"], True),       # 階層タグの親でも一致
    ("tag:会議", "a.md", ["会議録"], False),          # 前方一致ではない
    ("tag:Docker", "a.md", ["docker"], True),        # 大文字小文字は区別しない
    ("path:テスト", "テスト仕様/a.md", [], True),
    ("tag:会議 path:2024", "会議/2023.md", ["会議"], False),  # 条件はすべて満たす
])
def test_search_query_matches(query, path, tags, expected):
    assert parse_search_query(query).matches({"path": path, "tags": tags}) is expected


def test_search_index_applies_filter_before_limit():
    files = [
        {"path": f"other/{i}.md", "title": f"手順 {i}", "body_text": "手順", "tags": [], "published": True}
        for i in range(30)
    ] + [{"path": "会議/手順.md", "title": "手順", "body_text": "手順", "tags": ["会議"], "published": True}]
    idx = SearchIndex()
    idx.build(files)
    q = parse_search_query("手順 tag:会議")
    results = idx.search(q.text, True, files, limit=20, accept=q.matches)
    assert [r["path"] for r in results] == ["会議/手順.md"]
