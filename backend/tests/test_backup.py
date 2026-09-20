"""阶段 7：备份与恢复（测试方案 6.15 / 准出标准 E7）。

规格依据：spec 8 数据持久性 / 架构 11
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from app.backup import (
    create_backup,
    main,
    prune_backups,
    restore_backup,
    verify_backup,
)
from tests.support import build_running_scenario, create_attempt, submit


def seed_exam_data(client, clock):
    """产生一份有真实数据的数据库：1 场考试、2 名考生、1 份已交卷。"""
    scenario = build_running_scenario(client, clock, question_count=3)
    token = scenario.login("张三")
    attempt_id = create_attempt(client, token, scenario.exam_id).json()["attempt_id"]
    assert submit(client, token, attempt_id, scenario.answer_all_correct()).status_code == 200
    return scenario


def test_backup_file_is_valid_sqlite_with_matching_counts(client, clock, settings, tmp_path):
    """备份产出非空且合法的 SQLite，行数与源库一致。"""
    seed_exam_data(client, clock)

    backup_path = create_backup(settings.db_path, tmp_path / "backups")
    assert backup_path.exists()
    assert backup_path.stat().st_size > 0

    counts = verify_backup(backup_path)
    for table in ("users", "exams", "exam_candidates", "questions", "exam_questions",
                  "attempts", "answers"):
        assert table in counts, f"备份缺少表 {table}"
    assert counts["users"] == 2
    assert counts["exams"] == 1
    assert counts["exam_questions"] == 3
    assert counts["attempts"] == 1
    assert counts["answers"] == 3


def test_restore_recovers_same_data_volume(client, clock, settings, tmp_path):
    """从备份恢复后，exams/attempts/answers 数据量与备份时一致。"""
    seed_exam_data(client, clock)

    backup_path = create_backup(settings.db_path, tmp_path / "backups")
    expected = verify_backup(backup_path)

    restored_path = tmp_path / "restored.db"
    assert not restored_path.exists()
    restore_backup(backup_path, restored_path)

    actual = verify_backup(restored_path)
    assert actual == expected

    # 恢复后的库可直接被应用打开，且关键业务数据可读
    from app.db import create_db_engine
    from sqlmodel import Session, select

    from app.models import Attempt, Exam

    engine = create_db_engine(restored_path)
    with Session(engine) as session:
        attempts = list(session.exec(select(Attempt)).all())
        exams = list(session.exec(select(Exam)).all())
    assert len(attempts) == 1
    assert len(exams) == 1
    assert attempts[0].status == "submitted"
    assert attempts[0].score == 30.0


def test_restore_keeps_safety_copy_of_existing_db(client, clock, settings, tmp_path):
    """恢复会覆盖目标库，并把原库另存为 .pre-restore 以便回退。"""
    seed_exam_data(client, clock)
    backup_path = create_backup(settings.db_path, tmp_path / "backups")

    target = tmp_path / "target.db"
    # 目标库先放入一份「不同的」数据
    with sqlite3.connect(target) as conn:
        conn.execute("CREATE TABLE marker(x INTEGER)")
        conn.execute("INSERT INTO marker VALUES (1)")

    restore_backup(backup_path, target)

    safety = target.with_suffix(target.suffix + ".pre-restore")
    assert safety.exists(), "未生成恢复前安全副本"
    with sqlite3.connect(safety) as conn:
        assert conn.execute("SELECT COUNT(*) FROM marker").fetchone()[0] == 1


def test_verify_backup_rejects_non_sqlite(tmp_path):
    """非 SQLite 文件被拒绝。"""
    fake = tmp_path / "fake.db"
    fake.write_bytes(b"this is definitely not a database file")
    try:
        verify_backup(fake)
    except ValueError as exc:
        assert "SQLite" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("非法文件未被拒绝")


def test_verify_backup_rejects_empty(tmp_path):
    """空文件被拒绝。"""
    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    try:
        verify_backup(empty)
    except ValueError as exc:
        assert "空" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("空文件未被拒绝")


def test_create_backup_missing_database(tmp_path):
    """源库不存在 → 明确报错。"""
    try:
        create_backup(tmp_path / "nope.db", tmp_path / "backups")
    except FileNotFoundError:
        pass
    else:  # pragma: no cover
        raise AssertionError("缺失数据库未被报错")


def test_prune_backups_keeps_recent(tmp_path):
    """保留策略：删除超过保留期的备份，保留近期备份（至少 7 天）。"""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    now = datetime(2026, 9, 19, 12, 0, 0)
    old = backup_dir / "exam-20260901-120000.db"
    recent = backup_dir / "exam-20260918-120000.db"
    fresh = backup_dir / "exam-20260919-120000.db"
    for path in (old, recent, fresh):
        path.write_bytes(b"SQLite format 3\x00placeholder")

    removed = prune_backups(backup_dir, keep_days=7, now=now)

    assert old in removed
    assert recent.exists()
    assert fresh.exists()


def test_backup_cli_runs_end_to_end(client, clock, settings, tmp_path, capsys):
    """CLI 入口可完成备份并打印统计。"""
    seed_exam_data(client, clock)
    out_dir = tmp_path / "cli-backups"

    exit_code = main(["--db", str(settings.db_path), "--out", str(out_dir)])
    assert exit_code == 0

    captured = capsys.readouterr().out
    assert "备份完成" in captured
    assert "answers" in captured

    files = list(out_dir.glob("exam-*.db"))
    assert len(files) == 1
    assert verify_backup(files[0])["attempts"] == 1


def test_backup_cli_restore_roundtrip(client, clock, settings, tmp_path, capsys):
    """CLI 恢复路径可用。"""
    seed_exam_data(client, clock)
    backup_dir = tmp_path / "cli-backups"
    main(["--db", str(settings.db_path), "--out", str(backup_dir)])
    backup_file = next(backup_dir.glob("exam-*.db"))

    restored = tmp_path / "cli-restored.db"
    exit_code = main(["--db", str(restored), "--restore", str(backup_file)])
    assert exit_code == 0
    assert "已从" in capsys.readouterr().out
    assert verify_backup(restored)["attempts"] == 1


def test_hourly_backup_schedule_documented():
    """备份职责：每小时一次、保留 7 天（由部署层 cron 驱动）。

    此处断言模块暴露的默认保留策略，避免文档与实现漂移。
    """
    from app.backup import DEFAULT_KEEP_DAYS

    assert DEFAULT_KEEP_DAYS == 7


def test_backup_is_self_contained_single_file(client, clock, settings, tmp_path):
    """备份必须是单文件：不能留下 -wal/-shm 附属文件。

    架构 11 要求把备份拷到另一台机器或 NAS；若备份仍是 WAL 模式，
    只拷 .db 会丢掉还在 WAL 里的数据，等于备份不可用。
    """
    seed_exam_data(client, clock)

    backup_path = create_backup(settings.db_path, tmp_path / "backups")

    assert not (tmp_path / "backups" / (backup_path.name + "-wal")).exists()
    assert not (tmp_path / "backups" / (backup_path.name + "-shm")).exists()

    # 备份文件自身的日志模式应为 DELETE（非 WAL）
    with sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() != "wal"

    # 单独拷走这一个文件后，数据仍完整可读
    copied = tmp_path / "copied-to-nas.db"
    copied.write_bytes(backup_path.read_bytes())
    counts = verify_backup(copied)
    assert counts["attempts"] == 1
    assert counts["answers"] == 3


def test_prune_removes_wal_sidecars(tmp_path):
    """清理过期备份时一并删除 -wal/-shm，避免备份目录堆积。"""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    now = datetime(2026, 9, 19, 12, 0, 0)
    old = backup_dir / "exam-20260901-120000.db"
    old.write_bytes(b"SQLite format 3\x00old")
    (backup_dir / "exam-20260901-120000.db-wal").write_bytes(b"wal")
    (backup_dir / "exam-20260901-120000.db-shm").write_bytes(b"shm")

    removed = prune_backups(backup_dir, keep_days=7, now=now)

    assert old in removed
    assert not (backup_dir / "exam-20260901-120000.db-wal").exists()
    assert not (backup_dir / "exam-20260901-120000.db-shm").exists()
