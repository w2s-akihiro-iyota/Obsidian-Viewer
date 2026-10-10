"""ダッシュボードの「手入れが必要なノート」（F-6）: リンク切れ・孤立ノート・タグなしを数える

ページを開くたびにファイルを読み直さないよう、索引の作り直しで作ったキャッシュ
（各ノートの "missing_links"・BACKLINK_CACHE・"tags"）だけから作る。
ダッシュボードは管理者専用なので、非公開ノートも含めて数える。
"""
from dataclasses import dataclass

from app.config import DASHBOARD_CAUSE_NAME_COUNT


@dataclass(frozen=True)
class HealthRow:
    """表の 1 行"""
    file: dict      # GLOBAL_FILE_CACHE のノート
    cause: str      # 原因（リンク切れなら切れているリンク先の名前。ほかは空）


@dataclass(frozen=True)
class HealthCheck:
    """カード 1 枚と、その下に開く表"""
    id: str                     # 要素の id に使う（broken / orphan / untagged）
    label: str                  # カードの名前
    description: str            # カードの小さい説明
    rows: tuple[HealthRow, ...] # 該当ノートの全件（最終更新の新しい順）
    limit: int                  # 表に出す最大件数

    @property
    def count(self) -> int:
        return len(self.rows)

    @property
    def shown_rows(self) -> tuple[HealthRow, ...]:
        return self.rows[:self.limit]

    @property
    def hidden_count(self) -> int:
        """表に出ていない件数（「ほか N 件」）"""
        return max(self.count - self.limit, 0)


def _missing_cause(names: list[str]) -> str:
    """リンク切れの原因の文言（最大 3 件を「、」でつなぎ、残りは「ほか N 件」）"""
    cause = "、".join(names[:DASHBOARD_CAUSE_NAME_COUNT])
    if len(names) > DASHBOARD_CAUSE_NAME_COUNT:
        cause += f" ほか{len(names) - DASHBOARD_CAUSE_NAME_COUNT}件"
    return cause


def build_note_health(files: list[dict], backlinks: dict, limit: int) -> list[HealthCheck]:
    """
    3 種の「手入れが必要なノート」を作る

    - リンク切れ: 存在しないノートへのリンクを含むノート（判定は公開チェックと同じ。コードの中は数えない）
    - 孤立ノート: ほかのどのノートからもリンク・埋め込みされていないノート（自分へのリンクは数えない）
    - タグなし: frontmatter の tags が空のノート
    """
    newest_first = sorted(files, key=lambda f: f["mtime"], reverse=True)

    def check(id_: str, label: str, description: str, rows: list[HealthRow]) -> HealthCheck:
        return HealthCheck(id=id_, label=label, description=description, rows=tuple(rows), limit=limit)

    return [
        check("broken", "リンク切れ", "存在しないノートへのリンク",
              [HealthRow(f, _missing_cause(f.get("missing_links", []))) for f in newest_first if f.get("missing_links")]),
        check("orphan", "孤立ノート", "どこからもリンクされていない",
              [HealthRow(f, "") for f in newest_first if not backlinks.get(f["path"])]),
        check("untagged", "タグなし", "tags が空のノート",
              [HealthRow(f, "") for f in newest_first if not f.get("tags")]),
    ]
