"""SQLite 备份与恢复。

规格依据：spec 8 数据持久性 / 架构 11

要点：
    - 每小时执行一次 `.backup`（由外部 cron / launchd 调用本模块 CLI）。
    - 考试前手动备份一次。
    - 保留至少最近 7 天备份。
    - 备份使用 sqlite3 在线备份 API，WAL 模式下安全（不阻塞读、不需要停服）。
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_BACKUP_DIR = Path("data/backups")
DEFAULT_KEEP_DAYS = 7
_BACKUP_PREFIX = "exam-"
_BACKUP_SUFFIX = ".db"


def _timestamp(now: datetime | None = None) -> str:
    moment = now or datetime.now()
    return moment.strftime("%Y%m%d-%H%M%S")


def create_backup(
    db_path: Path | str,
    backup_dir: Path | str = DEFAULT_BACKUP_DIR,
    *,
    now: datetime | None = None,
) -> Path:
    """生成一份一致性备份，返回备份文件路径。

    使用 sqlite3 的在线备份 API：即使数据库处于 WAL 模式且正在被写入，
    也能得到一致的快照。
    """
    source = Path(db_path)
    if not source.exists():
        raise FileNotFoundError(f"数据库不存在：{source}")

    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{_BACKUP_PREFIX}{_timestamp(now)}{_BACKUP_SUFFIX}"

    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src_conn:
        with sqlite3.connect(target) as dst_conn:
            src_conn.backup(dst_conn)
            # 备份文件落到 DELETE 日志模式。
            # 否则备份会继承源库的 WAL 设置，在旁边留下 -wal/-shm 文件；
            # 只把这一个 .db 拷到 NAS 或另一台机器时，仍在 WAL 中的数据就会丢失。
            dst_conn.execute("PRAGMA journal_mode=DELETE")

    return target


def restore_backup(backup_path: Path | str, db_path: Path | str) -> Path:
    """从备份恢复数据库（覆盖目标文件）。

    恢复前会把现有数据库另存为 `.pre-restore` 副本，便于回退。
    """
    backup = Path(backup_path)
    if not backup.exists():
        raise FileNotFoundError(f"备份文件不存在：{backup}")

    target = Path(db_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        safety = target.with_suffix(target.suffix + ".pre-restore")
        if safety.exists():
            safety.unlink()
        target.replace(safety)

    with sqlite3.connect(backup) as src_conn:
        with sqlite3.connect(target) as dst_conn:
            src_conn.backup(dst_conn)

    return target


def verify_backup(backup_path: Path | str) -> dict:
    """校验备份文件是合法 SQLite 且可查询，返回表行数统计。"""
    path = Path(backup_path)
    if not path.exists():
        raise FileNotFoundError(f"备份文件不存在：{path}")
    if path.stat().st_size == 0:
        raise ValueError("备份文件为空")

    with open(path, "rb") as handle:
        header = handle.read(16)
    if not header.startswith(b"SQLite format 3"):
        raise ValueError("备份文件不是合法的 SQLite 数据库")

    counts: dict[str, int] = {}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        tables = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            counts[table] = conn.execute(f'SELECT COUNT(*) AS c FROM "{table}"').fetchone()["c"]
    return counts


def prune_backups(
    backup_dir: Path | str = DEFAULT_BACKUP_DIR,
    *,
    keep_days: int = DEFAULT_KEEP_DAYS,
    now: datetime | None = None,
) -> list[Path]:
    """删除超过保留期的备份，返回被删除的文件列表。"""
    directory = Path(backup_dir)
    if not directory.exists():
        return []

    cutoff = (now or datetime.now()) - timedelta(days=keep_days)
    removed: list[Path] = []
    for item in sorted(directory.glob(f"{_BACKUP_PREFIX}*{_BACKUP_SUFFIX}")):
        try:
            stamp = item.stem[len(_BACKUP_PREFIX):]
            created = datetime.strptime(stamp, "%Y%m%d-%H%M%S")
        except ValueError:
            continue
        if created < cutoff:
            item.unlink()
            removed.append(item)
            # 一并清理可能存在的 WAL 附属文件，避免备份目录堆积垃圾
            for suffix in ("-wal", "-shm"):
                sidecar = item.with_name(item.name + suffix)
                if sidecar.exists():
                    sidecar.unlink()
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SQLite 考试库备份 / 恢复工具")
    parser.add_argument("--db", default="data/exam.db", help="数据库路径")
    parser.add_argument("--out", default=str(DEFAULT_BACKUP_DIR), help="备份目录")
    parser.add_argument("--restore", metavar="BACKUP_FILE", help="从指定备份恢复")
    parser.add_argument("--keep-days", type=int, default=DEFAULT_KEEP_DAYS, help="备份保留天数")
    args = parser.parse_args(argv)

    if args.restore:
        target = restore_backup(args.restore, args.db)
        counts = verify_backup(target)
        print(f"已从 {args.restore} 恢复到 {target}")
        for table, count in sorted(counts.items()):
            print(f"  {table}: {count}")
        return 0

    backup = create_backup(args.db, args.out)
    counts = verify_backup(backup)
    removed = prune_backups(args.out, keep_days=args.keep_days)
    print(f"备份完成：{backup}（{Path(backup).stat().st_size} 字节）")
    for table, count in sorted(counts.items()):
        print(f"  {table}: {count}")
    if removed:
        print(f"清理过期备份 {len(removed)} 个")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
