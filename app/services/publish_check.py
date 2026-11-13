"""
公開チェック（F-5）: 外部の人がノートを開いたときに、何が見えなくなるかを調べる

管理者が「外部の人の表示」で確かめるための読み取り専用の処理。キャッシュは読むだけで書き換えない。
リンクの拾い方は描画と同じ iter_wikilinks を使い、描画で何がリンク切れになるかと食い違わないようにする。
埋め込んだ公開ノートの中身もページに出るので、描画と同じ条件（embeds_note・read_embed）でたどって同じ項目を調べる（X-5）。
"""
import logging
from dataclasses import dataclass
from pathlib import Path

from app import cache
from app.core.dataview import execute_query, parse_query
from app.services.wikilinks import (
    LinkKind, classify_link, embeds_note, is_missing_note, iter_fenced_blocks, iter_wikilinks, read_embed,
)

logger = logging.getLogger("app.publish_check")


@dataclass(frozen=True)
class NoteRef:
    """チェック結果に挙げるノート（パネルから管理者用の表示へ飛べるよう slug も持つ）"""
    title: str
    path: str
    slug: str


@dataclass(frozen=True)
class NoteIssue:
    """非公開ノートへのリンク・埋め込み 1 件"""
    note: NoteRef                 # リンク先の非公開ノート
    via: NoteRef | None = None    # リンクを書いてある、埋め込んだ公開ノート（ページ本体に書いてあれば None）


@dataclass(frozen=True)
class NameIssue:
    """存在しないノートへのリンク・見つからない画像 1 件"""
    name: str                     # リンクに書いた名前
    via: NoteRef | None = None    # リンクを書いてある、埋め込んだ公開ノート（ページ本体に書いてあれば None）


@dataclass(frozen=True)
class DataviewGap:
    """1 つの ```dataview ブロックで、外部の人には出ない結果"""
    query: str                      # クエリの 1 行目（パネルでどのブロックかを見分ける用）
    hidden: tuple[NoteRef, ...]     # 管理者には出るが外部には出ないノート
    via: NoteRef | None = None      # ブロックを書いてある、埋め込んだ公開ノート（ページ本体に書いてあれば None）

    @property
    def hidden_count(self) -> int:
        return len(self.hidden)


@dataclass(frozen=True)
class PublishCheck:
    """1 ノート分の公開チェックの結果"""
    is_private: bool                            # ノート自身が非公開（外部からは 404）
    private_links: tuple[NoteIssue, ...]        # 非公開ノートへのリンク（外部ではリンク切れの表示）
    private_embeds: tuple[NoteIssue, ...]       # 非公開ノートの埋め込み（外部では埋め込まれない）
    missing_links: tuple[NameIssue, ...]        # 存在しないノートへのリンク
    missing_images: tuple[NameIssue, ...]       # 見つからない画像（![[...]] に書いた名前）
    dataview_gaps: tuple[DataviewGap, ...]      # 外部では結果が減る Dataview ブロック
    # どれも、ページ本体のものが先、埋め込んだ公開ノートの中のものが後（via に埋め込んだノート）

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
    scan = _PageScan(source_path)
    scan.walk(body, stack=(source_path,), via=None)
    return PublishCheck(
        is_private=not is_published,
        private_links=tuple(scan.private_links.values()),
        private_embeds=tuple(scan.private_embeds.values()),
        missing_links=tuple(scan.missing_links.values()),
        missing_images=tuple(scan.missing_images.values()),
        dataview_gaps=tuple(scan.dataview_gaps),
    )


class _PageScan:
    """
    ページ本体と、そこに埋め込んだ公開ノートの中を、描画と同じ条件でたどって見つけたものを集める

    同じものでも、書いてある場所（ページ本体か、どの埋め込みか）が違えば別に挙げる（直す場所が違うため）。
    """

    def __init__(self, page_path: str):
        self.page_path = page_path
        self.files = {f["path"]: f for f in cache.GLOBAL_FILE_CACHE}
        self.published_paths = {path for path, f in self.files.items() if f.get("published")}
        # 出てきた順を保ったまま重複を除くため dict を使う。キーは (リンク先か名前, 書いてある場所)
        self.private_links: dict[tuple[str, str], NoteIssue] = {}
        self.private_embeds: dict[tuple[str, str], NoteIssue] = {}
        self.missing_links: dict[tuple[str, str], NameIssue] = {}
        self.missing_images: dict[tuple[str, str], NameIssue] = {}
        self.dataview_gaps: list[DataviewGap] = []
        # たどった埋め込み (ノート, 見出し)。同じものを 2 回埋め込んでも、中は 1 回だけ調べる（同じものを 2 回挙げない）
        self.walked: set[tuple[str, str]] = set()

    def note_ref(self, path: str) -> NoteRef:
        title = self.files.get(path, {}).get("title") or Path(path).stem
        return NoteRef(title=title, path=path, slug=cache.PATH_TO_SLUG.get(path, path))

    def walk(self, text: str, stack: tuple[str, ...], via: NoteRef | None) -> None:
        """
        text（ページ本体か、埋め込んだノートの本文）を調べ、埋め込んだ公開ノートの中もたどる

        stack は描画と同じく、ページのノートと、いま埋め込み中のノート（最後がリンクを書いたノート）。
        埋め込みの中は、その text の項目をすべて調べてからたどる（ページ本体のものを先に並べるため）。
        """
        where = via.path if via else ""
        embeds: list[tuple[str, str]] = []
        for link in iter_wikilinks(text):
            # 振り分けは描画（process_wikilinks）と同じ classify_link で行い、描画でリンク切れになるものと揃える
            target = classify_link(link, self.published_paths, source_path=stack[-1])
            if target.kind is LinkKind.MISSING_IMAGE:
                self.missing_images.setdefault((link.name, where), NameIssue(link.name, via))
            elif is_missing_note(link, target):   # ダッシュボードの「リンク切れ」と同じ判定
                self.missing_links.setdefault((link.name, where), NameIssue(link.name, via))
            elif target.kind is LinkKind.PRIVATE_NOTE and target.path != self.page_path:
                found = self.private_embeds if link.is_embed else self.private_links
                found.setdefault((target.path, where), NoteIssue(self.note_ref(target.path), via))
            elif embeds_note(link, target, stack, depth=len(stack) - 1):
                embeds.append((target.path, link.heading))
        self.dataview_gaps += _dataview_gaps(text, self.note_ref, via)

        for path, heading in embeds:
            if (path, heading) in self.walked:
                continue
            self.walked.add((path, heading))
            # 外部向けの描画と同じく、いま読んだファイルで公開を判定する。読めない・非公開（索引の作り直し待ち）・
            # 見出しの節が無いものは、描画でも中身が出ないのでたどらない
            embed = read_embed(path, heading, published_only=True)
            if embed.shown and embed.text is not None:
                self.walk(embed.text, stack + (path,), via=self.note_ref(path))


def _dataview_gaps(body: str, note_ref, via: NoteRef | None = None) -> list[DataviewGap]:
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
                                    hidden=tuple(note_ref(p) for p in hidden), via=via))
    return gaps
