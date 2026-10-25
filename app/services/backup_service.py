"""Backups of the data directory (documents, vectors, sessions, users).

Run on demand:      python -m app.services.backup_service
Scheduled:          main.py runs it every BACKUP_INTERVAL_HOURS while the server is up.
Restore:            stop the server, extract a backup into DATA_DIR, start the server.

Backups land in BACKUP_DIR as backup-YYYYMMDD-HHMMSS.tar.gz; only the newest
BACKUP_KEEP are kept. Put BACKUP_DIR on a different disk or sync it to cloud
storage for real disaster recovery - a backup on the same disk won't survive
losing that disk.
"""

import logging
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)


def _copy_sqlite(source: Path, target: Path) -> None:
    """Copy a SQLite database consistently, even while it is being written to."""
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)


def create_backup() -> Path:
    settings = get_settings()
    data_dir = settings.data_dir
    backup_dir = settings.backup_dir
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive = backup_dir / f"backup-{stamp}.tar.gz"

    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "data"
        # SQLite files (ChromaDB's catalogue) are copied with the backup API;
        # everything else is copied as-is.
        shutil.copytree(data_dir, snapshot, ignore=shutil.ignore_patterns("*.sqlite3*", "*.tmp"))
        for db in data_dir.rglob("*.sqlite3"):
            target = snapshot / db.relative_to(data_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            _copy_sqlite(db, target)

        with tarfile.open(archive, "w:gz") as tar:
            tar.add(snapshot, arcname=".")

    _prune(backup_dir, settings.backup_keep)
    logger.info("backup_created", extra={"path": str(archive), "bytes": archive.stat().st_size})
    return archive


def _prune(backup_dir: Path, keep: int) -> None:
    backups = sorted(backup_dir.glob("backup-*.tar.gz"))
    for old in backups[:-keep] if keep > 0 else []:
        old.unlink()
        logger.info("backup_pruned", extra={"path": str(old)})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(create_backup())
