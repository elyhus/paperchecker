# -*- coding: utf-8 -*-
"""报告输出：控制台表格、Markdown、JSON。"""
from __future__ import annotations

import json
from datetime import datetime

from .engine import CheckResult

SEV_ICON = {"错误": "✗", "警告": "!", "提示": "·"}


def console(result: CheckResult, limit: int | None = None) -> str:
    lines = []
    lines.append(f"文件：{result.path.name}")
    lines.append(f"耗时：{result.duration * 1000:.0f} ms")
    counts = result.counts
    lines.append(f"结果：错误 {counts['错误']} · 警告 {counts['警告']} · 提示 {counts['提示']}"
                 f"（可一键修复 {len(result.fixable)} 项）")
    lines.append("-" * 78)
    issues = result.issues if limit is None else result.issues[:limit]
    for issue in issues:
        icon = SEV_ICON[issue.severity.value]
        lines.append(f"{icon} [{issue.rule_id}] {issue.message}")
        if issue.location:
            lines.append(f"    {issue.location}")
        if issue.actual or issue.expected:
            lines.append(f"    实际：{issue.actual or '-'}    应为：{issue.expected or '-'}")
    if limit is not None and len(result.issues) > limit:
        lines.append(f"... 其余 {len(result.issues) - limit} 条见报告文件")
    if result.failed_rules:
        lines.append("-" * 78)
        lines.append("规则执行异常：")
        lines.extend(f"  · {item}" for item in result.failed_rules)
    return "\n".join(lines)


def rule_table(result: CheckResult) -> str:
    lines = ["规则             名称                          数量  级别"]
    lines.append("-" * 70)
    for stat in result.stats:
        lines.append(f"{stat.rule_id:<6} {stat.rule_name:<28} {stat.total:>4}  "
                     f"错{stat.error}/警{stat.warn}/提{stat.info}")
    return "\n".join(lines)


def markdown(result: CheckResult) -> str:
    counts = result.counts
    lines = [
        f"# 文档格式检查报告",
        "",
        f"- 文件：`{result.path.name}`",
        f"- 检查时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 耗时：{result.duration * 1000:.0f} ms",
        f"- 结果：错误 **{counts['错误']}** · 警告 **{counts['警告']}** · 提示 **{counts['提示']}**",
        f"- 可一键修复：**{len(result.fixable)}** 项",
        "",
        "## 问题清单",
        "",
        "| # | 级别 | 规则 | 位置 | 说明 | 实际 | 应为 |",
        "|---|---|---|---|---|---|---|",
    ]
    for idx, issue in enumerate(result.issues, 1):
        lines.append(
            f"| {idx} | {issue.severity.value} | `{issue.rule_id}` | {_cell(issue.location)} | "
            f"{_cell(issue.message)} | {_cell(issue.actual)} | {_cell(issue.expected)} |"
        )
    lines += ["", "## 规则统计", "", "| 规则 | 名称 | 数量 |", "|---|---|---|"]
    for stat in result.stats:
        lines.append(f"| `{stat.rule_id}` | {stat.rule_name} | {stat.total} |")
    return "\n".join(lines) + "\n"


def to_json(result: CheckResult) -> dict:
    return {
        "file": str(result.path),
        "duration_ms": round(result.duration * 1000, 1),
        "counts": result.counts,
        "issues": [issue.as_dict() for issue in result.issues],
        "stats": [stat.__dict__ for stat in result.stats],
    }


def dump_json(result: CheckResult, path) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(to_json(result), handle, ensure_ascii=False, indent=2)


def _cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")
