# -*- coding: utf-8 -*-
"""批处理：一次检查多个文档（选题单里的“批处理”）。

单个文件失败（加密、损坏、非 docx）不打断整批，只在汇总里记一条。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from . import engine, fixer
from .customrules import RuleConfig
from .model import Policy

SUFFIX = ".docx"


@dataclass
class BatchResult:
    results: list[engine.CheckResult] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    duration: float = 0.0

    @property
    def counts(self) -> dict[str, int]:
        total = {"错误": 0, "警告": 0, "提示": 0}
        for result in self.results:
            for key, value in result.counts.items():
                total[key] += value
        return total

    @property
    def fixable(self) -> int:
        return sum(len(result.fixable) for result in self.results)

    def worst(self, limit: int = 5) -> list[engine.CheckResult]:
        return sorted(self.results, key=lambda r: (-r.counts["错误"], -r.counts["警告"]))[:limit]


def collect(paths: list[str | Path]) -> list[Path]:
    """把文件夹展开成 docx 列表（递归一层）。"""
    out: list[Path] = []
    for item in paths:
        path = Path(item)
        if path.is_dir():
            out.extend(sorted(p for p in path.glob("*" + SUFFIX) if not p.name.startswith("~$")))
        elif path.suffix.lower() == SUFFIX:
            out.append(path)
    seen, unique = set(), []
    for path in out:
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def run_batch(paths: list[str | Path], config: RuleConfig | None = None) -> BatchResult:
    started = time.perf_counter()
    batch = BatchResult()
    for path in collect(paths):
        try:
            batch.results.append(engine.run(path, config=config))
        except Exception as exc:                      # 单个文件失败不影响整批
            batch.failed.append((path, str(exc)[:120]))
    batch.duration = time.perf_counter() - started
    return batch


def fix_batch(batch: BatchResult, config: RuleConfig | None = None) -> list[tuple[Path, Path, int]]:
    """修复所有可修复项；返回 [(文件, 备份, 修复条数)]。"""
    policy = config.policy() if config else Policy()
    report = []
    for result in batch.results:
        targets = result.fixable
        if not targets:
            continue
        backup_path, changes = fixer.apply(
            result.path, targets,
            policy_body_font=policy.body_font,
            policy_body_size=policy.body_size_pt,
            policy_line=policy.body_line_pt,
        )
        report.append((result.path, backup_path, len(changes)))
    return report


def summary_markdown(batch: BatchResult) -> str:
    counts = batch.counts
    lines = [
        "# 批量检查汇总",
        "",
        f"- 文件数：**{len(batch.results)}**"
        + (f"（失败 {len(batch.failed)}）" if batch.failed else ""),
        f"- 总耗时：{batch.duration:.1f} s",
        f"- 错误 **{counts['错误']}** · 警告 **{counts['警告']}** · 提示 **{counts['提示']}**",
        f"- 可一键修复：**{batch.fixable}** 处",
        "",
        "## 逐文件结果",
        "",
        "| 文件 | 错误 | 警告 | 提示 | 可修复 | 耗时 |",
        "|---|---|---|---|---|---|",
    ]
    for result in sorted(batch.results, key=lambda r: (-r.counts["错误"], -r.counts["警告"])):
        c = result.counts
        lines.append(f"| {result.path.name} | {c['错误']} | {c['警告']} | {c['提示']} "
                     f"| {len(result.fixable)} | {result.duration * 1000:.0f} ms |")
    if batch.failed:
        lines += ["", "## 打开失败", "", "| 文件 | 原因 |", "|---|---|"]
        for path, reason in batch.failed:
            lines.append(f"| {path.name} | {reason.replace('|', '/')} |")
    return "\n".join(lines) + "\n"
