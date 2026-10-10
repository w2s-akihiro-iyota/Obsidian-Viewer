"""
添付の置き場の引っ越し（S-5）

以前は Vault の添付を static/images（APP_IMAGES_DIR）に同期していた。/static はだれにでも配信されるため、
添付は MEDIA_DIR に移し、static/images にはアプリの部品（APP_IMAGE_ITEMS）だけを残す。
起動時に 1 回呼ぶ。移すものが無ければ何もしない。

消えて困るのは添付なので、移すときは「一時名にコピー → 大きさを確かめる → 名前を変える → 元を消す」の順にする。
移し先に同じ名前があれば、中身が同じ（大きさとハッシュが一致）ときだけ元を消し、違えば元を残して警告する。
"""
import hashlib
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.config import APP_IMAGES_DIR, MEDIA_DIR, MEDIA_SAMPLES_DIR_NAME

logger = logging.getLogger("app.media_migration")

# APP_IMAGES_DIR にあるアプリの部品の置き場（ヘルプの画像など。Git 管理）
APP_IMAGES_SAMPLES_DIR_NAME = "samples"

# APP_IMAGES_DIR に残すアプリの部品（直下の名前）。これ以外は MEDIA_DIR へ移す
APP_IMAGE_ITEMS = ("logo.png", APP_IMAGES_SAMPLES_DIR_NAME)

# 以前 APP_IMAGES_DIR/samples に置いていた、ノートのサンプルが参照する添付。MEDIA_DIR の同梱サンプルの置き場へ移す
LEGACY_SAMPLE_MEDIA = ("sample-image.png",)


@dataclass
class MigrationResult:
    """引っ越しの結果（ファイルの数）"""
    moved: int = 0     # MEDIA_DIR へ移した
    dropped: int = 0   # MEDIA_DIR に同じ中身があったので、元を消した
    kept: int = 0      # MEDIA_DIR に違う中身があった・移せなかったので、元を残した


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _same_content(a: Path, b: Path) -> bool:
    return a.stat().st_size == b.stat().st_size and _sha256(a) == _sha256(b)


def _move_file(src: Path, dest: Path, result: MigrationResult) -> None:
    """ファイル 1 つを移す。途中で失敗しても元は消さない"""
    if dest.exists() or dest.is_symlink():
        if dest.is_file() and _same_content(src, dest):
            src.unlink()
            result.dropped += 1
        else:
            logger.warning("Kept %s: %s already exists with different content.", src, dest)
            result.kept += 1
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.migrating")
    try:
        shutil.copy2(src, tmp)
        if tmp.stat().st_size != src.stat().st_size:
            raise OSError(f"size mismatch after copy: {tmp}")
        os.replace(tmp, dest)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        logger.warning("Kept %s: failed to copy to %s (%s).", src, dest, e)
        result.kept += 1
        return
    src.unlink()
    result.moved += 1


def _move_into(src: Path, dest: Path, result: MigrationResult) -> None:
    """src を dest へ移す。フォルダは中身ごとまとめる"""
    if src.is_dir() and not src.is_symlink():
        if dest.exists() and not dest.is_dir():
            logger.warning("Kept %s: %s already exists as a file.", src, dest)
            result.kept += sum(1 for p in src.rglob("*") if p.is_file())
            return
        for child in sorted(src.iterdir()):
            _move_into(child, dest / child.name, result)
        try:
            src.rmdir()
        except OSError:
            pass   # 残したものがあれば、フォルダも残す
        return
    _move_file(src, dest, result)


def _is_media_dir_persistent(images_dir: Path, media_dir: Path) -> bool:
    """
    移した添付がコンテナを作り直しても消えないか

    static をマウントしているのに media をマウントしていなければ、古い docker-compose.yml のまま
    再起動したコンテナと見なす（app/ もマウントしているので、コードだけ新しくなる）。
    そのまま移すとコンテナの中にだけ残り、作り直したときに消えるので移さない。
    """
    return not (os.path.ismount(images_dir.parent) and not os.path.ismount(media_dir))


def migrate_legacy_media(images_dir: Path = APP_IMAGES_DIR, media_dir: Path = MEDIA_DIR) -> MigrationResult:
    """
    images_dir 直下のアプリの部品（APP_IMAGE_ITEMS）以外を media_dir へ移す

    あわせて、以前 images_dir/samples に置いていたサンプルの添付（LEGACY_SAMPLE_MEDIA）を、
    media_dir の同梱サンプルの置き場（MEDIA_SAMPLES_DIR_NAME）へ移す。
    """
    result = MigrationResult()
    if not images_dir.is_dir():
        return result
    legacy = [item for item in sorted(images_dir.iterdir()) if item.name not in APP_IMAGE_ITEMS]
    legacy_samples = [images_dir / APP_IMAGES_SAMPLES_DIR_NAME / rel for rel in LEGACY_SAMPLE_MEDIA]
    legacy_samples = [p for p in legacy_samples if p.is_file()]
    if not legacy and not legacy_samples:
        return result

    if not _is_media_dir_persistent(images_dir, media_dir):
        logger.warning(
            "Skipped moving %d item(s) from %s: %s is not mounted. They are still public at /static/images/ "
            "until moved. Recreate the container with docker-compose up -d so that ./media is mounted.",
            len(legacy) + len(legacy_samples), images_dir, media_dir)
        return result

    for item in legacy:
        _move_into(item, media_dir / item.name, result)
    for src in legacy_samples:
        _move_into(src, media_dir / MEDIA_SAMPLES_DIR_NAME / src.name, result)

    logger.info("Moved %d attachment(s) from %s to %s (removed %d duplicate(s), kept %d).",
                result.moved, images_dir, media_dir, result.dropped, result.kept)
    return result
