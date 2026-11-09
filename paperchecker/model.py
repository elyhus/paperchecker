# -*- coding: utf-8 -*-
"""数据模型：一条检查结果就是一个 Issue。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    ERROR = "错误"
    WARN = "警告"
    INFO = "提示"

    @property
    def rank(self) -> int:
        return {"错误": 0, "警告": 1, "提示": 2}[self.value]


@dataclass
class Issue:
    rule_id: str
    rule_name: str
    severity: Severity
    message: str
    location: str = ""
    block_index: int = -1
    actual: str = ""
    expected: str = ""
    fixable: bool = False
    fix_kind: str | None = None
    fix_payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "message": self.message,
            "location": self.location,
            "block_index": self.block_index,
            "actual": self.actual,
            "expected": self.expected,
            "fixable": self.fixable,
        }


@dataclass
class Policy:
    """检查依据（可替换为其他学校的规范文件）。"""

    body_font: str = "宋体"
    body_size_pt: float = 12.0          # 小四
    body_line_pt: float = 20.0          # 固定值 20 磅
    body_min_chars: int = 20            # 参与正文格式检查的最短段落字数
    heading_font: str = "黑体"
    caption_font: str = "黑体"
    caption_size_pt: float = 10.5       # 五号
    latin_font: str = "Times New Roman"
    abstract_range: tuple[int, int] = (200, 300)
    keyword_range: tuple[int, int] = (3, 5)
    conclusion_range: tuple[int, int] = (400, 1000)
    min_refs: int = 10
    min_en_refs: int = 2


@dataclass
class RuleStats:
    rule_id: str
    rule_name: str
    total: int = 0
    error: int = 0
    warn: int = 0
    info: int = 0

    def add(self, issue: Issue) -> None:
        self.total += 1
        field = {Severity.ERROR: "error", Severity.WARN: "warn", Severity.INFO: "info"}[issue.severity]
        setattr(self, field, getattr(self, field) + 1)
