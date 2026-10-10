"""ダッシュボードのヒートマップ（D-8）: 最終更新日ごとの文字数を、週ごとの列のマスと月のラベルにする"""
from datetime import datetime, timedelta

from app.config import DASHBOARD_HEATMAP_WEEKS, HEATMAP_LEVEL_LIMITS, HEATMAP_MONTH_LABEL_MIN_GAP

# マスの濃さの段数（0 文字の段を含む）。テンプレートの凡例と CSS の .level-N はこの数に合わせる
HEATMAP_LEVEL_COUNT = len(HEATMAP_LEVEL_LIMITS) + 2   # 0 文字の段 + 区切りで分けた段（区切りの数 + 1）


def heatmap_level(chars: int) -> int:
    """その日に更新したノートの文字数の合計から、マスの濃さ（0〜HEATMAP_LEVEL_COUNT-1）を決める"""
    if chars == 0:
        return 0
    for level, limit in enumerate(HEATMAP_LEVEL_LIMITS, start=1):
        if chars <= limit:
            return level
    return HEATMAP_LEVEL_COUNT - 1


def build_heatmap(files: list[dict], now: datetime) -> tuple[list[dict], list[dict]]:
    """
    ヒートマップのマス（日曜始まりで 1 列 1 週、DASHBOARD_HEATMAP_WEEKS 列）と月のラベルを作る

    月のラベルは、その月の 1 日を含む週の列（1 始まり）に置く。
    """
    daily_chars: dict[str, int] = {}
    for f in files:
        updated_str = f.get("updated")
        if updated_str:
            # "2026-04-14 10:17" のような値の日付の部分だけを使う
            date_str = updated_str[:10]
            daily_chars[date_str] = daily_chars.get(date_str, 0) + f.get("char_count", 0)

    today = now.date()
    this_sunday = today - timedelta(days=(today.weekday() + 1) % 7)
    start = this_sunday - timedelta(weeks=DASHBOARD_HEATMAP_WEEKS - 1)

    heatmap_data = []
    month_labels: list[dict] = []
    for i in range((today - start).days + 1):
        day = start + timedelta(days=i)
        column = i // 7 + 1
        if i == 0 or day.day == 1:
            if month_labels and column - month_labels[-1]["column"] < HEATMAP_MONTH_LABEL_MIN_GAP:
                month_labels.pop()
            month_labels.append({"label": f"{day.month}月", "title": f"{day.year}年{day.month}月", "column": column})
        d_str = day.strftime("%Y-%m-%d")
        chars = daily_chars.get(d_str, 0)
        heatmap_data.append({"date": d_str, "count": chars, "level": heatmap_level(chars)})

    # 右端に近いラベルは、枠からはみ出さないよう列の右端にそろえる
    for label in month_labels:
        label["span"] = min(HEATMAP_MONTH_LABEL_MIN_GAP, DASHBOARD_HEATMAP_WEEKS - label["column"] + 1)
        label["at_end"] = label["span"] < HEATMAP_MONTH_LABEL_MIN_GAP
    return heatmap_data, month_labels
