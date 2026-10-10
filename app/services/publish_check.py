"""
公開チェック（F-5）: 外部の人がノートを開いたときに、何が見えなくなるかを調べる

管理者が「外部の人の表示」で確かめるための読み取り専用の処理。キャッシュは読むだけで書き換えない。
リンクの拾い方は描画と同じ iter_wikilinks を使い、描画で何がリンク切れになるかと食い違わないようにする。
"""
import logging
from dataclasses import dataclass
from pathlib import Path

from app import cache
from app.core.dataview import execute_query, parse_query
from app.services.wikilinks import LinkKind, classify_link, is_missing_note, iter_fenced_blocks, iter_wikilinks

logger = logging.getLogger("app.publish_check")


@dataclass(frozen=True)
class NoteRef:
    """チェック結果に挙げるノート（パネルから管理者用の表示へ飛べるよう slug も持つ）"""
    title: str
    path: str
    slug: str


@dataclass(frozen=True)
class DataviewGap:
    """1 つの ```dataview ブロックで、外部の人には出ない結果"""
    query: str                      # クエリの 1 行目（パネルでどのブロックかを見分ける用）
    hidden: tuple[NoteRef, ...]     # 管理者には出るが外部には出ないノート

    @property
    def hidden_count(self) -> int:
        return len(self.hidden)


@dataclass(frozen=True)
class PublishCheck:
    """1 ノート分の公開チェックの結果"""
    is_private: bool                            # ノート自身が非公開（外部からは 403）
    private_links: tuple[NoteRef, ...]          # 非公開ノートへのリンク（外部ではリンク切れの表示）
    private_embeds: tuple[NoteRef, ...]         # 非公開ノートの埋め込み（外部では埋め込まれない）
    missing_links: tuple[str, ...]              # 存在しないノートへのリンク（リンクに書いた名前）
    missing_images: tuple[str, ...]             # 見つからない画像（![[...]] に書いた名前）
    dataview_gaps: tuple[DataviewGap, ...]      # 外部では結果が減る Dataview ブロック

    @property
    def issue_count(self) -> int:
        """要確認の件数。ノート・画像は 1 件ずつ、Dataview は結果が減るブロック 1 つを 1 件と数える"""
        return (int(self.is_private) + len(self.private_links) + len(self.private_embeds)
                + len(self.missing_links) + len(self.missing_images) + len(self.dataview_gaps))


def check_publish(source_path: str, body: str, is_published: bool) -> PublishCheck:
    """
    ノート 1 件の公開チェックを行う

    source_path: ノートの相対パス（自分自身へのリンクは数えない）
    body: frontmatter を除いた本文
    is_published: ノート自身が公開か（描画と同じく、いま読んだファイルの frontmatter で判定した値を渡す）
    """
    files = {f["path"]: f for f in cache.GLOBAL_FILE_CACHE}

    def note_ref(path: str) -> NoteRef:
        title = files.get(path, {}).get("title") or Path(path).stem
        return NoteRef(title=title, path=path, slug=cache.PATH_TO_SLUG.get(path, path))

    # 出てきた順を保ったまま重複を除くため dict を使う
    private_links: dict[str, NoteRef] = {}
    private_embeds: dict[str, NoteRef] = {}
    missing_links: dict[str, None] = {}
    missing_images: dict[str, None] = {}

    published_paths = {path for path, f in files.items() if f.get("published")}
    for link in iter_wikilinks(body):
        # 振り分けは描画（process_wikilinks）と同じ classify_link で行い、描画でリンク切れになるものと揃える
        target = classify_link(link, published_paths)
        if target.kind is LinkKind.MISSING_IMAGE:
            missing_images.setdefault(link.name)
        elif is_missing_note(link, target):   # ダッシュボードの「リンク切れ」と同じ判定
            missing_links.setdefault(link.name)
        elif target.kind is LinkKind.PRIVATE_NOTE and target.path != source_path:
            (private_embeds if link.is_embed else private_links).setdefault(target.path, note_ref(target.path))

    return PublishCheck(
        is_private=not is_published,
        private_links=tuple(private_links.values()),
        private_embeds=tuple(private_embeds.values()),
        missing_links=tuple(missing_links),
        missing_images=tuple(missing_images),
        dataview_gaps=tuple(_dataview_gaps(body, note_ref)),
    )


def _dataview_gaps(body: str, note_ref) -> list[DataviewGap]:
    """```dataview ブロックごとに、全件で実行した結果と公開ノートだけで実行した結果の差を取る"""
    gaps = []
    for info, text in iter_fenced_blocks(body):
        if info != "dataview":
            continue
        try:
            query = parse_query(text)
            shown = {f["path"] for f in execute_query(query, published_only=True)}
            hidden = [f["path"] for f in execute_query(query, published_only=False) if f["path"] not in shown]
        except Exception as e:
            # 書き方の誤りは、描画でも外部向けでも同じエラー表示になるので差には数えない
            logger.debug("公開チェックで Dataview を実行できませんでした: %s", e)
            continue
        if hidden:
            gaps.append(DataviewGap(query=text.strip().split('\n', 1)[0],
                                    hidden=tuple(note_ref(p) for p in hidden)))
    return gaps
