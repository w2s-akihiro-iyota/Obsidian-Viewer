"""パスのスラッグ化ユーティリティ（日本語→ローマ字変換）"""
import re
import pykakasi

_kakasi = pykakasi.kakasi()


def slugify_segment(text: str) -> str:
    """単一パスセグメントをスラッグ化"""
    result = _kakasi.convert(text)
    romaji = "".join([item['hepburn'] for item in result])
    romaji = romaji.lower()
    romaji = re.sub(r'[^a-z0-9]+', '-', romaji)
    return romaji.strip('-')


def slugify_path(file_path: str) -> str:
    """ファイルパス全体をスラッグ化（.md除去 + 各セグメント変換）"""
    if file_path.endswith('.md'):
        file_path = file_path[:-3]
    segments = file_path.split('/')
    return '/'.join(slugify_segment(seg) for seg in segments if seg)
