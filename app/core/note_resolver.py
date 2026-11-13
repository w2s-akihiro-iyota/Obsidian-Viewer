"""[[name]] の name からノートを引く（描画・バックリンク・公開チェックで共通のルール）"""
from typing import Iterable, NamedTuple


class NoteEntry(NamedTuple):
    """ノート 1 件。view_path はビューアのパス、vault_path は Vault のルートからのパス（分からなければ None）"""
    view_path: str
    vault_path: str | None


class NoteResolver:
    """
    ノート名・パスからビューアのパスを引く読み取り専用の表

    索引の作り直しのたびに作り直す（更新メソッドは持たない）。
    entries は (ビューアのパス, Vault のルートからのパス or None) の列。
    aliases は (別名, ビューアのパス) の列（frontmatter の aliases。X-2）。ファイル名・パスで見つからないときだけ引く。
    結果は entries・aliases の並び順に依存しない（同名の選び方はパスだけで決まる）。
    """

    def __init__(self, entries: Iterable[tuple[str, str | None]], aliases: Iterable[tuple[str, str]] = ()):
        self._by_stem: dict[str, list[NoteEntry]] = {}
        for view_path, vault_path in entries:
            self._by_stem.setdefault(self._stem(view_path), []).append(NoteEntry(view_path, vault_path))
        self._by_alias: dict[str, set[str]] = {}
        for alias, view_path in aliases:
            self._by_alias.setdefault(alias, set()).add(view_path)

    @staticmethod
    def _stem(path: str) -> str:
        """パスのファイル名（拡張子なし）"""
        name = path.rpartition("/")[2]
        return name[:-3] if name.endswith(".md") else name

    def has_stem(self, stem: str) -> bool:
        """そのファイル名（拡張子なし）のノートがあるか"""
        return stem in self._by_stem

    def resolve(self, name: str, source_path: str = "") -> str | None:
        """
        [[name]] の指すノートのビューアのパスを返す。無ければ None

        - "/" を含まない名前: ファイル名（拡張子なし）が同じノート
        - "/" を含む名前: ビューアのパスか Vault のパスが「name.md」と完全一致するもの。
          無ければ、どちらかが「/name.md」で終わるもの（段の区切りで末尾一致）
        - どちらでも見つからなければ、frontmatter の別名（aliases）が name のノート
        - 候補が複数なら、リンク元と同じフォルダ → パスの段数が少ない → パスの辞書順
        """
        name = name.lstrip("/")
        if name.endswith(".md"):
            name = name[:-3]
        if not name:
            return None
        candidates = self._by_stem.get(name.rpartition("/")[2], [])
        if "/" in name:
            target = f"{name}.md"
            matched = [c for c in candidates if target in (c.view_path, c.vault_path)]
            if not matched:
                suffix = f"/{target}"
                matched = [c for c in candidates if any(p and p.endswith(suffix) for p in (c.view_path, c.vault_path))]
            candidates = matched
        view_paths = [c.view_path for c in candidates] or self._by_alias.get(name, ())
        if not view_paths:
            return None
        source_dir = source_path.rpartition("/")[0] if source_path else None
        return min(
            view_paths,
            key=lambda p: (0 if source_dir is not None and p.rpartition("/")[0] == source_dir else 1,
                           p.count("/"), p),
        )
