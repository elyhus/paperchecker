# -*- coding: utf-8 -*-
"""本地数据存储（SQLite）：规则、任务、问题明细、修复记录、模型配置。

对应设计文档中的数据模型，字段名与第 3 章表结构一致，方便报告直接引用。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .engine import CheckResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS t_model_config (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    provider      TEXT NOT NULL,
    base_url      TEXT NOT NULL,
    model_name    TEXT NOT NULL,
    api_key_cipher TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS t_check_task (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name   TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    error_count INTEGER NOT NULL,
    warn_count  INTEGER NOT NULL,
    info_count  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS t_issue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES t_check_task(id) ON DELETE CASCADE,
    rule_id     TEXT NOT NULL,
    rule_name   TEXT NOT NULL,
    severity    TEXT NOT NULL,
    location    TEXT,
    block_index INTEGER,
    actual      TEXT,
    expected    TEXT,
    message     TEXT,
    fixed       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS t_rule (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id      TEXT NOT NULL,
    name         TEXT NOT NULL,
    category     TEXT,
    severity     TEXT,
    expect_value TEXT,
    enabled      INTEGER NOT NULL DEFAULT 1,
    source       TEXT NOT NULL DEFAULT 'config',
    description  TEXT
);

CREATE TABLE IF NOT EXISTS t_semantic_result (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id      INTEGER NOT NULL REFERENCES t_check_task(id) ON DELETE CASCADE,
    check_type   TEXT,
    model_output TEXT,
    suggestion   TEXT,
    confidence   REAL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS t_fix_record (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES t_check_task(id) ON DELETE CASCADE,
    block_index INTEGER,
    field      TEXT,
    before     TEXT,
    after      TEXT,
    backup_path TEXT,
    fixed_at   TEXT NOT NULL
);
"""


def connect(db_path: str | Path = "paperchecker.db") -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path))
    connection.executescript(SCHEMA)
    connection.row_factory = sqlite3.Row
    return connection


def save_result(result: CheckResult, db_path: str | Path = "paperchecker.db") -> int:
    counts = result.counts
    connection = connect(db_path)
    with connection:
        cursor = connection.execute(
            "INSERT INTO t_check_task(file_name, file_path, started_at, duration_ms,"
            " error_count, warn_count, info_count) VALUES (?,?,?,?,?,?,?)",
            (result.path.name, str(result.path), datetime.now().isoformat(timespec="seconds"),
             int(result.duration * 1000), counts["错误"], counts["警告"], counts["提示"]),
        )
        task_id = int(cursor.lastrowid)
        connection.executemany(
            "INSERT INTO t_issue(task_id, rule_id, rule_name, severity, location, block_index,"
            " actual, expected, message) VALUES (?,?,?,?,?,?,?,?,?)",
            [(task_id, i.rule_id, i.rule_name, i.severity.value, i.location, i.block_index,
              i.actual, i.expected, i.message) for i in result.issues],
        )
    connection.close()
    return task_id


def save_model_config(provider: str, base_url: str, model_name: str,
                      db_path: str | Path = "paperchecker.db") -> None:
    """只记录用哪个厂商/模型；密钥本体在系统密钥链里，这里写占位。"""
    connection = connect(db_path)
    with connection:
        connection.execute(
            "INSERT INTO t_model_config(provider, base_url, model_name, api_key_cipher, created_at)"
            " VALUES (?,?,?,?,?)",
            (provider, base_url, model_name, "keychain",
             datetime.now().isoformat(timespec="seconds")),
        )
    connection.close()


def save_fixes(task_id: int, changes, backup_path: str,
               db_path: str | Path = "paperchecker.db") -> None:
    connection = connect(db_path)
    with connection:
        connection.executemany(
            "INSERT INTO t_fix_record(task_id, block_index, field, before, after, backup_path, fixed_at)"
            " VALUES (?,?,?,?,?,?,?)",
            [(task_id, c.block_index, c.field, c.before, c.after, backup_path,
              datetime.now().isoformat(timespec="seconds")) for c in changes],
        )
    connection.close()


def recent_tasks(limit: int = 10, db_path: str | Path = "paperchecker.db") -> list[dict]:
    connection = connect(db_path)
    rows = connection.execute(
        "SELECT * FROM t_check_task ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    connection.close()
    return [dict(row) for row in rows]


def recent_issues(task_id: int, db_path: str | Path = "paperchecker.db") -> list[dict]:
    connection = connect(db_path)
    rows = connection.execute(
        "SELECT * FROM t_issue WHERE task_id = ? ORDER BY severity DESC", (task_id,)
    ).fetchall()
    connection.close()
    return [dict(row) for row in rows]


def stats_overview(db_path: str | Path = "paperchecker.db") -> dict:
    connection = connect(db_path)
    row = connection.execute(
        "SELECT COUNT(*) AS tasks, COALESCE(SUM(error_count),0) AS errors,"
        " COALESCE(SUM(warn_count),0) AS warns FROM t_check_task"
    ).fetchone()
    connection.close()
    return json.loads(json.dumps(dict(row)))


def save_semantic(task_id: int, payload: dict, db_path: str | Path = "paperchecker.db") -> None:
    """语义检查的原始返回（已脱敏，不含 Key）。"""
    connection = connect(db_path)
    with connection:
        connection.execute(
            "INSERT INTO t_semantic_result(task_id, check_type, model_output, suggestion, confidence,"
            " created_at) VALUES (?,?,?,?,?,?)",
            (task_id, "document", json.dumps(payload, ensure_ascii=False),
             str(payload.get("comment", ""))[:200], None,
             datetime.now().isoformat(timespec="seconds")),
        )
    connection.close()


def sync_rules(config, db_path: str | Path = "paperchecker.db") -> int:
    """把当前规则配置同步进 t_rule，便于审计“这次检查用的是哪版规则”。"""
    connection = connect(db_path)
    count = 0
    with connection:
        connection.execute("DELETE FROM t_rule WHERE source = 'config'")
        for rule in config.rules:
            connection.execute(
                "INSERT INTO t_rule(rule_id, name, category, severity, expect_value, enabled,"
                " source, description) VALUES (?,?,?,?,?,?,?,?)",
                (rule.id, rule.name, rule.type, rule.severity.value,
                 json.dumps(rule.to_dict(), ensure_ascii=False), int(rule.enabled),
                 "config", rule.message),
            )
            count += 1
    connection.close()
    return count
