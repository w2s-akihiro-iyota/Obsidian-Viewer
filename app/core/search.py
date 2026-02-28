"""TF-IDF全文検索エンジン（外部依存なし）"""
import math
import re
import logging
import unicodedata

logger = logging.getLogger("app.search")

# CJK文字範囲の判定
_CJK_RANGES = (
    ('\u3040', '\u309f'),  # ひらがな
    ('\u30a0', '\u30ff'),  # カタカナ
    ('\u4e00', '\u9fff'),  # CJK統合漢字
    ('\u3400', '\u4dbf'),  # CJK統合漢字拡張A
    ('\uf900', '\ufaff'),  # CJK互換漢字
)

_ASCII_WORD_RE = re.compile(r'[a-zA-Z0-9_]+')


def _is_cjk(ch: str) -> bool:
    """文字がCJK（日本語含む）かどうか判定"""
    for lo, hi in _CJK_RANGES:
        if lo <= ch <= hi:
            return True
    return False


def tokenize(text: str) -> list[str]:
    """テキストをトークン化。ASCII=単語分割、CJK=バイグラム"""
    text = text.lower()
    tokens = []
    cjk_buf = []

    i = 0
    while i < len(text):
        ch = text[i]

        if _is_cjk(ch):
            cjk_buf.append(ch)
            i += 1
        else:
            # CJKバッファをフラッシュ（バイグラム生成）
            if cjk_buf:
                cjk_str = ''.join(cjk_buf)
                if len(cjk_str) == 1:
                    tokens.append(cjk_str)
                else:
                    for j in range(len(cjk_str) - 1):
                        tokens.append(cjk_str[j:j+2])
                cjk_buf = []

            # ASCII単語を抽出
            m = _ASCII_WORD_RE.match(text, i)
            if m:
                tokens.append(m.group())
                i = m.end()
            else:
                i += 1

    # 残りのCJKバッファをフラッシュ
    if cjk_buf:
        cjk_str = ''.join(cjk_buf)
        if len(cjk_str) == 1:
            tokens.append(cjk_str)
        else:
            for j in range(len(cjk_str) - 1):
                tokens.append(cjk_str[j:j+2])

    return tokens


def tokenize_query(query: str) -> list[str]:
    """クエリ用トークン化（tokenizeと同じロジック）"""
    return tokenize(query)


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
        # 総文書数
        self.doc_count: int = 0

    def build(self, file_cache: list[dict]) -> None:
        """GLOBAL_FILE_CACHEからインデックスを構築"""
        self.inverted_index = {}
        self.doc_lengths = {}
        self.title_index = {}
        self.path_index = {}
        self.doc_count = len(file_cache)

        for f in file_cache:
            path = f["path"]
            body_text = f.get("body_text", "")
            title = f.get("title", "")

            # 本文インデックス
            body_tokens = tokenize(body_text)
            self.doc_lengths[path] = len(body_tokens)
            for pos, token in enumerate(body_tokens):
                if token not in self.inverted_index:
                    self.inverted_index[token] = {}
                if path not in self.inverted_index[token]:
                    self.inverted_index[token][path] = []
                self.inverted_index[token][path].append(pos)

            # タイトルインデックス
            title_tokens = tokenize(title)
            for pos, token in enumerate(title_tokens):
                if token not in self.title_index:
                    self.title_index[token] = {}
                if path not in self.title_index[token]:
                    self.title_index[token][path] = []
                self.title_index[token][path].append(pos)

            # パスインデックス
            path_tokens = tokenize(path)
            for pos, token in enumerate(path_tokens):
                if token not in self.path_index:
                    self.path_index[token] = {}
                if path not in self.path_index[token]:
                    self.path_index[token][path] = []
                self.path_index[token][path].append(pos)

        logger.info(
            "検索インデックス構築完了: %d文書, %d語彙",
            self.doc_count, len(self.inverted_index)
        )

    def _score_document(self, path: str, query_tokens: list[str]) -> float:
        """TF-IDF計算（対数TF + log IDF）。タイトル・パスにボーナス加算"""
        score = 0.0
        doc_len = self.doc_lengths.get(path, 1)

        for token in query_tokens:
            # 本文スコア
            postings = self.inverted_index.get(token, {})
            if path in postings:
                tf = len(postings[path])
                log_tf = 1 + math.log(tf) if tf > 0 else 0
                df = len(postings)
                idf = math.log((self.doc_count + 1) / (df + 1))
                score += log_tf * idf

            # タイトルボーナス（3倍重み）
            title_postings = self.title_index.get(token, {})
            if path in title_postings:
                tf = len(title_postings[path])
                log_tf = 1 + math.log(tf) if tf > 0 else 0
                df = len(title_postings)
                idf = math.log((self.doc_count + 1) / (df + 1))
                score += log_tf * idf * 3.0

            # パスボーナス（1.5倍重み）
            path_postings = self.path_index.get(token, {})
            if path in path_postings:
                tf = len(path_postings[path])
                log_tf = 1 + math.log(tf) if tf > 0 else 0
                df = len(path_postings)
                idf = math.log((self.doc_count + 1) / (df + 1))
                score += log_tf * idf * 1.5

        return score

    def _generate_snippet(self, body_text: str, query_tokens: set[str],
                          max_len: int = 120) -> str:
        """マッチ箇所前後のスニペットを生成"""
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

        if best_pos < 0:
            # フォールバック: 先頭を返す
            return body_text[:max_len] + ("..." if len(body_text) > max_len else "")

        start = best_pos
        end = min(len(body_text), start + max_len)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(body_text) else ""
        return prefix + body_text[start:end] + suffix

    def search(self, query: str, is_localhost: bool, file_cache: list[dict],
               limit: int = 20) -> list[dict]:
        """TF-IDFスコア付き検索を実行"""
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
                f.get("body_text", ""), query_token_set
            )

            results.append({
                "title": f["title"],
                "path": f["path"],
                "snippet": snippet,
                "score": round(score, 4),
            })

        return results
