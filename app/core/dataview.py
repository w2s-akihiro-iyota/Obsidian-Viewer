"""Dataviewフェンスブロックのパーサー・実行エンジン・HTMLレンダラー"""
import re
import logging
from datetime import datetime
from html import escape

from app import cache

logger = logging.getLogger("app.dataview")


class DataviewQuery:
    """パース済みDataviewクエリ構造体"""

    def __init__(self):
        self.query_type: str = ""       # "TABLE" or "LIST"
        self.fields: list[str] = []     # TABLEのフィールド一覧
        self.from_folder: str = ""      # FROM "folder" のフォルダパス
        self.from_tag: str = ""         # FROM #tag のタグ名
        self.where_conditions: list[tuple] = []  # [(field, op, value), ...]
        self.sort_field: str = ""
        self.sort_order: str = "DESC"   # ASC or DESC
        self.limit: int = 0             # 0 = 無制限


# ビルトインフィールド名のマッピング
_BUILTIN_FIELDS = {
    "title", "path", "tags", "reading_time", "char_count",
    "mtime", "updated", "published",
}


def parse_query(text: str) -> DataviewQuery:
    """クエリ文字列をパース"""
    q = DataviewQuery()
    text = text.strip()

    # クエリタイプ判定
    upper = text.upper()
    if upper.startswith("TABLE"):
        q.query_type = "TABLE"
        rest = text[5:].strip()
        # フィールドリスト（FROMの前まで）
        from_match = re.search(r'\bFROM\b', rest, re.IGNORECASE)
        if from_match:
            fields_str = rest[:from_match.start()].strip()
            rest = rest[from_match.start():]
        else:
            # FROMなし: WHERE/SORT/LIMITを探す
            kw_match = re.search(r'\b(WHERE|SORT|LIMIT)\b', rest, re.IGNORECASE)
            if kw_match:
                fields_str = rest[:kw_match.start()].strip()
                rest = rest[kw_match.start():]
            else:
                fields_str = rest
                rest = ""

        if fields_str:
            q.fields = [f.strip() for f in fields_str.split(",") if f.strip()]
    elif upper.startswith("LIST"):
        q.query_type = "LIST"
        rest = text[4:].strip()
    else:
        raise ValueError(f"未対応のクエリタイプ: {text[:20]}")

    # FROM "folder" または FROM #tag
    from_folder_match = re.match(r'FROM\s+"([^"]+)"', rest, re.IGNORECASE)
    from_tag_match = re.match(r'FROM\s+#(\S+)', rest, re.IGNORECASE)
    if from_folder_match:
        q.from_folder = from_folder_match.group(1).strip().strip("/")
        rest = rest[from_folder_match.end():].strip()
    elif from_tag_match:
        q.from_tag = from_tag_match.group(1).strip()
        rest = rest[from_tag_match.end():].strip()
    else:
        # FROMが他の形式（マッチしない場合）でもスキップして次の句に進む
        from_skip = re.match(r'FROM\s+\S+', rest, re.IGNORECASE)
        if from_skip:
            rest = rest[from_skip.end():].strip()

    # WHERE条件（AND結合のみ）
    where_match = re.match(r'WHERE\s+(.+?)(?=\s+SORT\b|\s+LIMIT\b|$)', rest, re.IGNORECASE | re.DOTALL)
    if where_match:
        where_str = where_match.group(1).strip()
        rest = rest[where_match.end():].strip()

        # AND分割
        parts = re.split(r'\s+AND\s+', where_str, flags=re.IGNORECASE)
        for part in parts:
            cond = _parse_condition(part.strip())
            if cond:
                q.where_conditions.append(cond)

    # SORT field ASC|DESC
    sort_match = re.match(r'SORT\s+(\S+)(?:\s+(ASC|DESC))?', rest, re.IGNORECASE)
    if sort_match:
        q.sort_field = sort_match.group(1).strip()
        if sort_match.group(2):
            q.sort_order = sort_match.group(2).upper()
        rest = rest[sort_match.end():].strip()

    # LIMIT n
    limit_match = re.match(r'LIMIT\s+(\d+)', rest, re.IGNORECASE)
    if limit_match:
        q.limit = int(limit_match.group(1))

    return q


def _parse_condition(text: str) -> tuple | None:
    """単一WHERE条件をパース -> (field, operator, value)"""
    # フィールド名はドット付き (file.name, file.path等) も許容
    field_re = r'([\w.]+)'

    # contains演算子
    m = re.match(field_re + r'\s+contains\s+"([^"]*)"', text, re.IGNORECASE)
    if m:
        return (m.group(1), "contains", m.group(2))

    m = re.match(field_re + r'\s+contains\s+(\S+)', text, re.IGNORECASE)
    if m:
        return (m.group(1), "contains", m.group(2))

    # 比較演算子（値がクォート付き）
    m = re.match(field_re + r'\s*(!=|>=|<=|>|<|=)\s*"([^"]*)"', text)
    if m:
        return (m.group(1), m.group(2), m.group(3))

    # 比較演算子（値がクォートなし）
    m = re.match(field_re + r'\s*(!=|>=|<=|>|<|=)\s*(\S+)', text)
    if m:
        return (m.group(1), m.group(2), m.group(3))

    return None


# Obsidian Dataviewの file.* プロパティ → キャッシュキーのマッピング
_FILE_PROP_MAP = {
    # file.name は拡張子なし(stem)を返す特殊処理のためマップに含めない
    "file.path": "path",          # 相対パス
    "file.folder": "_folder",     # 親フォルダ（特殊処理）
    "file.tags": "tags",
    "file.mtime": "mtime",
    "file.ctime": "mtime",        # ctime は mtime で代用
    "file.size": "char_count",
}


def _get_field_value(file_entry: dict, field: str):
    """ファイルエントリからフィールド値を取得"""
    # file.* プロパティ (Obsidian Dataview互換)
    if field.startswith("file."):
        mapped = _FILE_PROP_MAP.get(field)
        if mapped == "_folder":
            path = file_entry.get("path", "")
            parts = path.rsplit("/", 1)
            return parts[0] if len(parts) > 1 else ""
        if mapped:
            return file_entry.get(mapped)
        # file.name は Dataview では拡張子なし（stem）を返す
        if field == "file.name":
            name = file_entry.get("name", "")
            return name.rsplit(".", 1)[0] if "." in name else name
        if field == "file.link" or field == "file.stem":
            name = file_entry.get("name", "")
            return name.rsplit(".", 1)[0] if "." in name else name
        return None

    # ビルトインフィールド
    if field in file_entry:
        return file_entry[field]

    # frontmatterから取得
    fm = file_entry.get("frontmatter", {})
    if field in fm:
        return fm[field]

    return None


def _evaluate_condition(file_entry: dict, field: str, op: str, value: str) -> bool:
    """条件を評価"""
    actual = _get_field_value(file_entry, field)

    if actual is None:
        return op == "!="

    # contains演算子
    if op == "contains":
        if isinstance(actual, list):
            return value in actual
        return value.lower() in str(actual).lower()

    # 文字列比較
    actual_str = str(actual)

    # boolean判定
    if value.lower() in ("true", "false"):
        actual_bool = actual is True or str(actual).lower() == "true"
        value_bool = value.lower() == "true"
        if op == "=":
            return actual_bool == value_bool
        if op == "!=":
            return actual_bool != value_bool

    # 数値判定
    try:
        actual_num = float(actual_str)
        value_num = float(value)
        if op == "=":
            return actual_num == value_num
        if op == "!=":
            return actual_num != value_num
        if op == ">":
            return actual_num > value_num
        if op == ">=":
            return actual_num >= value_num
        if op == "<":
            return actual_num < value_num
        if op == "<=":
            return actual_num <= value_num
    except (ValueError, TypeError):
        pass

    # 文字列比較フォールバック
    if op == "=":
        return actual_str == value
    if op == "!=":
        return actual_str != value
    if op == ">":
        return actual_str > value
    if op == ">=":
        return actual_str >= value
    if op == "<":
        return actual_str < value
    if op == "<=":
        return actual_str <= value

    return False


def execute_query(query: DataviewQuery) -> list[dict]:
    """GLOBAL_FILE_CACHEに対してクエリを実行"""
    results = []

    for f in cache.GLOBAL_FILE_CACHE:
        # FROMフィルタ（フォルダ）
        if query.from_folder:
            if not f["path"].startswith(query.from_folder + "/"):
                continue

        # FROMフィルタ（タグ）
        if query.from_tag:
            file_tags = f.get("tags") or []
            if query.from_tag not in file_tags:
                continue

        # WHEREフィルタ（全条件AND）
        match = True
        for field, op, value in query.where_conditions:
            if not _evaluate_condition(f, field, op, value):
                match = False
                break
        if not match:
            continue

        results.append(f)

    # SORT
    if query.sort_field:
        reverse = query.sort_order == "DESC"

        def sort_key(item):
            val = _get_field_value(item, query.sort_field)
            if val is None:
                return ""
            if isinstance(val, datetime):
                return val.isoformat()
            return str(val)

        results.sort(key=sort_key, reverse=reverse)

    # LIMIT
    if query.limit > 0:
        results = results[:query.limit]

    return results


def _format_field_value(value, field: str = "") -> str:
    """フィールド値をHTML表示用にフォーマット"""
    if value is None:
        return '<span class="dataview-null">-</span>'

    if isinstance(value, bool) or (isinstance(value, str) and value.lower() in ("true", "false")):
        is_true = value is True or (isinstance(value, str) and value.lower() == "true")
        cls = "dataview-badge-true" if is_true else "dataview-badge-false"
        label = "true" if is_true else "false"
        return f'<span class="{cls}">{label}</span>'

    if isinstance(value, list):
        # タグリストの場合
        parts = []
        for item in value:
            parts.append(f'<span class="dataview-tag">{escape(str(item))}</span>')
        return " ".join(parts)

    if isinstance(value, datetime):
        return escape(value.strftime("%Y-%m-%d %H:%M"))

    return escape(str(value))


def render_table(query: DataviewQuery, results: list[dict]) -> str:
    """TABLE結果をHTMLテーブルとしてレンダリング"""
    fields = query.fields if query.fields else ["title", "tags", "updated"]

    header_cells = '<th>File</th>'
    for field in fields:
        header_cells += f'<th>{escape(field)}</th>'

    rows = ""
    for f in results:
        title = escape(f.get("title", ""))
        slug = escape(cache.PATH_TO_SLUG.get(f.get("path", ""), f.get("path", "")))
        link = f'<a href="/view/{slug}" class="dataview-link">{title}</a>'
        row_cells = f'<td>{link}</td>'

        for field in fields:
            val = _get_field_value(f, field)
            row_cells += f'<td>{_format_field_value(val, field)}</td>'

        rows += f'<tr>{row_cells}</tr>\n'

    return f"""<div class="dataview-container">
<table class="dataview-table">
<thead><tr>{header_cells}</tr></thead>
<tbody>{rows}</tbody>
</table>
<div class="dataview-footer">{len(results)}件の結果</div>
</div>"""


_NOTE_ICON = '<svg class="dataview-note-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 13H8"/><path d="M16 13h-2"/><path d="M10 17H8"/><path d="M16 17h-2"/></svg>'


def render_list(query: DataviewQuery, results: list[dict]) -> str:
    """LIST結果をノートアイコン付き箇条書きHTMLとしてレンダリング"""
    items = ""
    for f in results:
        title = escape(f.get("title", ""))
        slug = escape(cache.PATH_TO_SLUG.get(f.get("path", ""), f.get("path", "")))
        items += (
            f'<li>'
            f'<a href="/view/{slug}" class="dataview-list-link">'
            f'{_NOTE_ICON}'
            f'<span class="dataview-list-title">{title}</span>'
            f'</a>'
            f'</li>\n'
        )

    return f"""<div class="dataview-container">
<ul class="dataview-list">{items}</ul>
<div class="dataview-footer">{len(results)}件の結果</div>
</div>"""


def render_error(message: str) -> str:
    """エラーをHTMLとして表示（ページはクラッシュさせない）"""
    return f'<div class="dataview-error">Dataview Error: {escape(message)}</div>'


def process_dataview(text: str) -> str:
    """メインエントリポイント: Dataviewクエリ文字列を受け取りHTMLを返す"""
    try:
        query = parse_query(text)
        results = execute_query(query)

        if query.query_type == "TABLE":
            return render_table(query, results)
        elif query.query_type == "LIST":
            return render_list(query, results)
        else:
            return render_error(f"未対応のクエリタイプ: {query.query_type}")
    except Exception as e:
        logger.warning("Dataviewクエリ実行エラー: %s", e)
        return render_error(str(e))
