"""TF-IDF全文検索エンジン（外部依存なし）"""
import math
import re
import logging
import unicodedata
from dataclasses import dataclass, field
from typing import Callable

from app import cache as app_cache

logger = logging.getLogger("app.search")

# CJK文字範囲の判定
_CJK_RANGES = (
    ('\u3040', '\u309f'),  # ひらがな
    ('\u30a0', '\u30ff'),  # カタカナ
    ('\u4e00', '\u9fff'),  # CJK統合漢字
    ('\u3400', '\u4dbf'),  # CJK統合漢字拡張A
    ('\uf900', '\ufaff'),  # CJK互換漢字
)


def _is_cjk(ch: str) -> bool:
    """文字がCJK（日本語含む）かどうか判定"""
    for lo, hi in _CJK_RANGES:
        if lo <= ch <= hi:
            return True
    return False


def normalize_text(text: str) -> str:
    """検索用に正規化する（NFKC で全角英数字・半角カナをそろえ、小文字にする）"""
    return unicodedata.normalize("NFKC", text).lower()


# CJK の連続 / それ以外の英数字・_ の連続。\w は str.isalnum() または _ と同じ範囲なので、
# 以前の 1 文字ずつの判定（_char_kind）と同じ切り方になる。正規表現にして Python のループを避ける（Q-20）
_CJK_CLASS = "぀-ゟ゠-ヿ一-鿿㐀-䶿豈-﫿"
_TOKEN_RE = re.compile(rf"(?P<cjk>[{_CJK_CLASS}]+)|(?P<word>[^\W{_CJK_CLASS}]+)")


def tokenize(text: str) -> list[str]:
    """テキストをトークン化。英数字など=単語分割、CJK=バイグラム"""
    tokens = []
    for m in _TOKEN_RE.finditer(normalize_text(text)):
        if m.lastgroup == "word":
            tokens.append(m.group())
        else:
            cjk_str = m.group()
            if len(cjk_str) == 1:
                tokens.append(cjk_str)
            else:
                tokens.extend([cjk_str[j:j + 2] for j in range(len(cjk_str) - 1)])
    return tokens


# 検索の対象にする frontmatter のキー（F-13）と、その重み。タイトル（3.0）より下、本文（1.0）より上
META_KEYS = ("keywords", "summary", "description", "aliases")
META_WEIGHT = 2.0
TITLE_WEIGHT = 3.0
PATH_WEIGHT = 1.5


def _value_text(value) -> str:
    """frontmatter の値 1 つを文字列にする（配列は空白でつなぐ。数値などは文字列にする。無いものは空）"""
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(t for t in (_value_text(v) for v in value) if t)
    return str(value).strip()


def frontmatter_search_text(frontmatter) -> str:
    """frontmatter の keywords・summary・description・aliases を 1 つの文字列にする（無い・壊れた frontmatter は空）"""
    if not isinstance(frontmatter, dict):
        return ""
    return " ".join(t for t in (_value_text(frontmatter.get(k)) for k in META_KEYS) if t)


def _snippet_fallback(frontmatter) -> str:
    """本文に当たりが無いときの抜粋（summary、無ければ description）"""
    if not isinstance(frontmatter, dict):
        return ""
    return _value_text(frontmatter.get("summary")) or _value_text(frontmatter.get("description"))


def tokenize_query(query: str) -> list[str]:
    """クエリ用トークン化（tokenizeと同じロジック）"""
    return tokenize(query)


# tag:会議 / path:テスト仕様 / path:"スペース 入り"
_FILTER_RE = re.compile(r'(?<!\S)(tag|path):(?:"([^"]*)"|(\S+))', re.IGNORECASE)


@dataclass
class SearchQuery:
    """検索語と絞り込み条件（tag: / path:）に分けたクエリ"""
    text: str
    tags: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)

    @property
    def has_filters(self) -> bool:
        return bool(self.tags or self.paths)

    def matches(self, f: dict) -> bool:
        """ノートが絞り込み条件をすべて満たすか（tag は階層タグの親でも一致、path は部分一致）"""
        note_tags = [str(t).lower() for t in (f.get("tags") or [])]
        for tag in self.tags:
            if not any(t == tag or t.startswith(tag + "/") for t in note_tags):
                return False
        note_path = f.get("path", "").lower()
        return all(p in note_path for p in self.paths)


def parse_search_query(q: str) -> SearchQuery:
    """クエリ文字列から tag: / path: を取り出し、残りを検索語にする"""
    tags, paths = [], []
    for m in _FILTER_RE.finditer(q):
        value = (m.group(2) if m.group(2) is not None else m.group(3)).strip().lower()
        if not value:
            continue
        if m.group(1).lower() == "tag":
            tags.append(value.lstrip("#"))
        else:
            paths.append(value)
    text = " ".join(_FILTER_RE.sub(" ", q).split())
    return SearchQuery(text=text, tags=tags, paths=paths)


class SearchIndex:
    """転置インデックス + TF-IDFスコアリングの検索エンジン"""

    def __init__(self):
        # {term: {doc_path: [positions]}}
        self.inverted_index: dict[str, dict[str, list[int]]] = {}
        # 文書ごとのトークン数
        self.doc_lengths: dict[str, int] = {}
        # タイトル用インデックス
        self.title_index: dict[str, dict[str, list[int]]] = {}
        # パス用インデックス
        self.path_index: dict[str, dict[str, list[int]]] = {}
        # メタ情報（frontmatter の keywords など）用インデックス
        self.meta_index: dict[str, dict[str, list[int]]] = {}
        # 総文書数
        self.doc_count: int = 0
        # {path: ((本文, タイトル, メタ情報), 本文のトークン数, 4 つの索引ごとの {term: [positions]})}。次の build で使い回す
        self._doc_tokens: dict[str, tuple] = {}

    def build(self, file_cache: list[dict], previous: "SearchIndex | None" = None) -> None:
        """
        GLOBAL_FILE_CACHEからインデックスを構築

        previous（前回の索引）を渡すと、本文・タイトル・パス・メタ情報が前回と同じノートはトークンを使い回し、
        転置インデックスの組み立てだけをやり直す（Q-20）。
        """
        self.inverted_index = {}
        self.doc_lengths = {}
        self.title_index = {}
        self.path_index = {}
        self.meta_index = {}
        self.doc_count = len(file_cache)
        self._doc_tokens = {}
        last_tokens = previous._doc_tokens if previous is not None else {}

        for f in file_cache:
            path = f["path"]
            body_text = f.get("body_text", "")
            title = f.get("title", "")
            meta = frontmatter_search_text(f.get("frontmatter"))

            key = (body_text, title, meta)
            cached = last_tokens.get(path)
            if cached is not None and cached[0] == key:
                length, postings = cached[1], cached[2]
            else:
                body_tokens = tokenize(body_text)
                length = len(body_tokens)
                postings = (self._group_positions(body_tokens), self._group_positions(tokenize(title)),
                            self._group_positions(tokenize(path)), self._group_positions(tokenize(meta)))
            self._doc_tokens[path] = (key, length, postings)

            self.doc_lengths[path] = length
            # 本文・タイトル・パス・メタ情報（keywords・summary・description・aliases）の各インデックスへ
            for index, doc_postings in zip(
                    (self.inverted_index, self.title_index, self.path_index, self.meta_index), postings):
                for token, positions in doc_postings.items():
                    index.setdefault(token, {})[path] = positions

        logger.info(
            "検索インデックス構築完了: %d文書, %d語彙",
            self.doc_count, len(self.inverted_index)
        )

    @staticmethod
    def _group_positions(tokens: list[str]) -> dict[str, list[int]]:
        """トークン列を {term: [positions]} にまとめる（ノートごと。変わらなければ次の build で使い回す）"""
        grouped: dict[str, list[int]] = {}
        for pos, token in enumerate(tokens):
            grouped.setdefault(token, []).append(pos)
        return grouped

    def _field_score(self, index: dict[str, dict[str, list[int]]], token: str, path: str, weight: float) -> float:
        """1 つの索引（本文・タイトル・メタ・パス）での、token の TF-IDF スコア × 重み"""
        postings = index.get(token)
        if not postings or path not in postings:
            return 0.0
        tf = len(postings[path])
        log_tf = 1 + math.log(tf) if tf > 0 else 0
        idf = math.log((self.doc_count + 1) / (len(postings) + 1))
        return log_tf * idf * weight

    def _score_document(self, path: str, query_tokens: list[str]) -> float:
        """TF-IDF計算（対数TF + log IDF）。タイトル・メタ情報・パスにボーナス加算"""
        score = 0.0
        for token in query_tokens:
            score += self._field_score(self.inverted_index, token, path, 1.0)
            score += self._field_score(self.title_index, token, path, TITLE_WEIGHT)
            # メタ情報（keywords など）は本文より上・タイトルより下の重み
            score += self._field_score(self.meta_index, token, path, META_WEIGHT)
            score += self._field_score(self.path_index, token, path, PATH_WEIGHT)
        return score

    def _generate_snippet(self, body_text: str, query_tokens: set[str],
                          max_len: int = 120, fallback: str = "") -> str:
        """マッチ箇所前後のスニペットを生成（本文に当たりが無く fallback があれば、その先頭を返す）"""
        # 検索語と同じく正規化して探す。長さが変わる文字（㍿ など）があるときは位置がずれるので小文字にするだけにする
        text_lower = normalize_text(body_text)
        if len(text_lower) != len(body_text):
            text_lower = body_text.lower()
        best_pos = -1
        best_density = 0

        # スライディングウィンドウでマッチ密度が最大の箇所を探す
        window = max_len
        for start in range(0, max(1, len(body_text) - window + 1), 20):
            chunk = text_lower[start:start + window]
            density = sum(1 for t in query_tokens if t in chunk)
            if density > best_density:
                best_density = density
                best_pos = start
            if best_density >= len(query_tokens):
                break

        if best_pos < 0 and fallback:
            # 本文に当たりが無い（keywords などで当たった）ときは、要約を見せる
            return fallback[:max_len] + ("..." if len(fallback) > max_len else "")
        if best_pos < 0:
            # フォールバック: 先頭を返す
            return body_text[:max_len] + ("..." if len(body_text) > max_len else "")

        start = best_pos
        end = min(len(body_text), start + max_len)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(body_text) else ""
        return prefix + body_text[start:end] + suffix

    def search(self, query: str, is_localhost: bool, file_cache: list[dict],
               limit: int = 20, accept: Callable[[dict], bool] | None = None) -> list[dict]:
        """TF-IDFスコア付き検索を実行（accept を渡すと、それを満たすノートだけを対象にする）"""
        query_tokens = tokenize_query(query)
        if not query_tokens:
            return []

        query_token_set = set(query_tokens)

        # 候補文書を収集（いずれかのトークンを含む文書）
        candidate_paths: set[str] = set()
        for token in query_token_set:
            if token in self.inverted_index:
                candidate_paths.update(self.inverted_index[token].keys())
            if token in self.title_index:
                candidate_paths.update(self.title_index[token].keys())
            if token in self.path_index:
                candidate_paths.update(self.path_index[token].keys())
            if token in self.meta_index:
                candidate_paths.update(self.meta_index[token].keys())

        # 公開フィルタ用のルックアップ
        published_set = None
        if not is_localhost:
            published_set = {f["path"] for f in file_cache if f.get("published")}

        # ファイル情報のルックアップ
        file_lookup = {f["path"]: f for f in file_cache}

        # スコアリングと結果構築
        scored_results = []
        for path in candidate_paths:
            if published_set is not None and path not in published_set:
                continue
            if accept is not None and (path not in file_lookup or not accept(file_lookup[path])):
                continue

            score = self._score_document(path, query_tokens)
            if score > 0:
                scored_results.append((path, score))

        # スコア降順ソート
        scored_results.sort(key=lambda x: x[1], reverse=True)

        # 結果を構築
        results = []
        for path, score in scored_results[:limit]:
            f = file_lookup.get(path)
            if not f:
                continue

            snippet = self._generate_snippet(
                f.get("body_text", ""), query_token_set,
                fallback=_snippet_fallback(f.get("frontmatter"))
            )

            results.append({
                "title": f["title"],
                "path": f["path"],
                "slug": app_cache.PATH_TO_SLUG.get(f["path"], f["path"]),
                "snippet": snippet,
                "score": round(score, 4),
            })

        return results
