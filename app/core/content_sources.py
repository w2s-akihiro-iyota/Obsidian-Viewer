"""同期元とビューア内の置き場所の対応表

ノートの同期元は 1 つ（元フォルダ。content/ の直下にそのまま置く）に加えて、追加の同期元
（例: Vault 直下の llm-wiki を content/llm-wiki/ に置く）を持てる。
「ビューアのこのパスは、どの同期元の、どのファイルか」を引くのはここだけにして、
同期・エディタの保存先・索引がそれぞれ別の規則で引かないようにする。

設定（SyncConfig）から作る読み取り専用の表で、作ったあとは変えない。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.config import PROTECTED_ITEMS
from app.models.sync import ExtraSource, SyncConfig
from app.utils.messages import get_error

# 置き場所の名前に使えない文字（Windows のファイル名に使えないものと、パスの区切り）
_DEST_FORBIDDEN_CHARS = '/\\:*?"<>|'


def normalize_exclude(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """
    運ばないパスの指定をそろえる

    前後の空白と / を除き、バックスラッシュは / にする。空になったものは捨て、重複は最初の 1 つだけ残す。
    """
    result: list[str] = []
    for value in values:
        path = value.strip().replace("\\", "/").strip("/").strip()
        if path and path not in result:
            result.append(path)
    return tuple(result)


def check_dest(dest: str) -> str:
    """
    追加の同期元の置き場所として使えない理由を返す。使えるなら空文字

    1 段の名前で、. で始まらず、区切りや Windows で使えない文字を含まず、アプリが使う名前（samples 等）でないこと。
    ほかの置き場所との重なりは、全体を見ないと分からないので ContentSources 側で見る。
    """
    if (not dest or dest != dest.strip() or dest.startswith(".")
            or any(c in _DEST_FORBIDDEN_CHARS for c in dest) or dest in PROTECTED_ITEMS):
        return get_error("E005")
    return ""


def _collides(origin_src: Path, dest: str) -> bool:
    """元フォルダの直下に、置き場所と同じ名前があるか"""
    return (origin_src / dest).exists()


def extra_source_problems(extra_sources: list[ExtraSource], content_src: str = "",
                          check_filesystem: bool = False) -> list[tuple[int, str, str]]:
    """
    追加の同期元の設定の問題を [(行の添字, "src" か "dest", エラー文)] で返す

    追加の同期元の規則はここ 1 か所に置く（対応表の作成と、設定の保存の検証が同じものを使う）。
    check_filesystem が真なら、保存のときだけ見るものも返す
    （src のフォルダが無い・元フォルダ content_src の直下に同じ名前がある）。
    置き場所の重なりは、問題の無い前の行とだけ比べる（問題のある行は使われないため）。
    """
    problems: list[tuple[int, str, str]] = []
    ok_dests: set[str] = set()
    for i, extra in enumerate(extra_sources):
        before = len(problems)
        if not extra.src:
            problems.append((i, "src", get_error("E001")))
        elif check_filesystem and not Path(extra.src).is_dir():
            problems.append((i, "src", get_error("E002")))

        if reason := check_dest(extra.dest):
            problems.append((i, "dest", reason))
        elif extra.dest in ok_dests:
            problems.append((i, "dest", get_error("E006")))
        elif check_filesystem and content_src and _collides(Path(content_src), extra.dest):
            problems.append((i, "dest", get_error("E007")))

        if len(problems) == before:
            ok_dests.add(extra.dest)
    return problems


@dataclass(frozen=True)
class ContentSource:
    """同期元 1 つ。dest はビューア内の置き場所（元フォルダは ""）"""
    src: Path
    dest: str = ""
    exclude: tuple[str, ...] = ()
    # src から親へさかのぼって最初に .obsidian がある場所（Vault のルート）。無ければ None
    vault_root: Path | None = field(default=None, compare=False)
    # Vault のルートから src までの / 区切りのパス（src がルートそのものなら ""）。ルートが無ければ None
    vault_prefix: str | None = field(default=None, compare=False)

    def is_excluded(self, rel: str) -> bool:
        """rel（同期元からの / 区切りのパス）を運ばないか。ドットで始まる段があるもの・exclude に当たるもの"""
        if any(part.startswith(".") for part in rel.split("/")):
            return True
        return any(rel == ex or rel.startswith(ex + "/") for ex in self.exclude)

    def view_path(self, rel: str) -> str:
        """同期元からのパスを、ビューア内のパスにする"""
        return rel if not self.dest else f"{self.dest}/{rel}"


def _find_vault_root(src: Path) -> tuple[Path | None, str | None]:
    """
    (Vault のルート, ルートから src までのパス)。ルートは src 自身を含め、親へさかのぼって最初に .obsidian がある場所

    ファイルシステムに触るので、作るとき（from_config）に 1 回だけ呼ぶ。見つからなければ (None, None)。
    """
    resolved = src.resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".obsidian").is_dir():
            prefix = resolved.relative_to(candidate).as_posix()
            return candidate, "" if prefix == "." else prefix
    return None, None


@dataclass(frozen=True)
class ContentSources:
    """元フォルダと、使える追加の同期元の対応表"""
    origin: ContentSource | None
    extras: tuple[ContentSource, ...] = ()
    # 置き場所などが使えず、同期にも保存先にもリンクにも使わない追加の同期元と、その理由
    invalid: tuple[tuple[ExtraSource, str], ...] = ()

    @classmethod
    def from_config(cls, config: SyncConfig) -> ContentSources:
        origin = None
        if config.content_src:
            src = Path(config.content_src)
            root, prefix = _find_vault_root(src)
            origin = ContentSource(src=src, vault_root=root, vault_prefix=prefix)

        # 行ごとの最初の問題（ファイルシステムは見ない）。あれば使わない
        reasons: dict[int, str] = {}
        for i, _field, message in extra_source_problems(config.extra_sources):
            reasons.setdefault(i, message)

        extras: list[ContentSource] = []
        invalid: list[tuple[ExtraSource, str]] = []
        for i, extra in enumerate(config.extra_sources):
            if i in reasons:
                invalid.append((extra, reasons[i]))
            else:
                src = Path(extra.src)
                root, prefix = _find_vault_root(src)
                extras.append(ContentSource(src=src, dest=extra.dest, exclude=normalize_exclude(extra.exclude),
                                            vault_root=root, vault_prefix=prefix))
        return cls(origin=origin, extras=tuple(extras), invalid=tuple(invalid))

    def _split(self, view_path: str) -> tuple[ContentSource | None, str]:
        """(同期元, 置き場所を除いた残りのパス)"""
        head, _, rest = view_path.partition("/")
        for extra in self.extras:
            if head == extra.dest:
                return extra, rest
        if head in PROTECTED_ITEMS:
            return None, ""
        return self.origin, view_path

    def source_of(self, view_path: str) -> ContentSource | None:
        """ビューアのパスが属する同期元。samples など同期の対象外は None"""
        return self._split(view_path)[0]

    def host_path(self, view_path: str) -> Path | None:
        """
        ビューアのパスに対応する同期元側のパス（存在は見ない。呼ぶ側が is_file を確かめる）

        同期元の外に出るパス・運ばないパスは None。
        """
        source, rest = self._split(view_path)
        if source is None or not rest:
            return None
        base = source.src.resolve()
        resolved = (base / rest).resolve()
        if base not in resolved.parents:
            return None
        if source.is_excluded(resolved.relative_to(base).as_posix()):
            return None
        return resolved

    def vault_path(self, view_path: str) -> str | None:
        """
        ビューアのパスに対応する、Vault のルートからの / 区切りのパス。ルートが無ければ None

        索引の作り直しで何度も呼ばれる（バインドマウント越しだと 1 回ごとに遅い）ので、
        ファイルシステムには触れず、作るときに求めた前置きと文字列だけで組み立てる。
        host_path と同じく、同期元の外へ出るパス・運ばないパスは None。
        """
        source, rest = self._split(view_path)
        if source is None or source.vault_prefix is None or not rest:
            return None
        if rest.startswith("/") or any(part in ("", ".", "..") for part in rest.split("/")):
            return None
        if source.is_excluded(rest):
            return None
        return f"{source.vault_prefix}/{rest}" if source.vault_prefix else rest

    def protected_for(self, source: ContentSource) -> list[str]:
        """同期で消さないコピー先の直下の名前。元フォルダは、追加の同期元の置き場所も守る"""
        if source.dest:
            return []
        # 使えない追加の同期元も、置き場所の名前として使える形なら守る（同期を飛ばしても、コピー先を消さないため）
        names = [e.dest for e in self.extras] + [e.dest for e, _ in self.invalid if not check_dest(e.dest)]
        return PROTECTED_ITEMS + list(dict.fromkeys(names))

    def conflicts(self) -> list[ContentSource]:
        """置き場所と同じ名前が、元フォルダの直下にある追加の同期元（どちらのものか決められない）"""
        if self.origin is None:
            return []
        return [e for e in self.extras if _collides(self.origin.src, e.dest)]
