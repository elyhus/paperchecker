# -*- coding: utf-8 -*-
"""规则执行引擎：跑规则、聚合、排序，单条规则异常不影响整体。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from . import customrules
from . import rules as rules_module
from .docmodel import ParsedDoc
from .model import Issue, Policy, RuleStats, Severity


@dataclass
class CheckResult:
    path: Path
    doc: ParsedDoc
    issues: list[Issue]
    stats: list[RuleStats]
    duration: float
    failed_rules: list[str] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "错误": sum(1 for i in self.issues if i.severity is Severity.ERROR),
            "警告": sum(1 for i in self.issues if i.severity is Severity.WARN),
            "提示": sum(1 for i in self.issues if i.severity is Severity.INFO),
        }

    @property
    def fixable(self) -> list[Issue]:
        return [i for i in self.issues if i.fixable]


def run(path: str | Path, policy: Policy | None = None,
        only: list[str] | None = None, min_severity: Severity | None = None,
        config: "customrules.RuleConfig | None" = None) -> CheckResult:
    if config is not None and policy is None:
        policy = config.policy()          # 用户自定义的参数覆盖默认规范
    policy = policy or Policy()
    started = time.perf_counter()
    doc = ParsedDoc(path)

    issues: list[Issue] = []
    stats: dict[str, RuleStats] = {}
    failed: list[str] = []

    for rule_def in rules_module.RULES:
        if only and rule_def.rule_id not in only:
            continue
        try:
            found = rule_def.check(doc, policy) or []
        except Exception as exc:                      # 单条规则失败不阻断整体
            failed.append(f"{rule_def.rule_id} {rule_def.name}: {exc}")
            continue
        for issue in found:
            issue.rule_id = issue.rule_id or rule_def.rule_id
            issue.rule_name = issue.rule_name or rule_def.name
            issues.append(issue)
            stats.setdefault(issue.rule_id,
                             RuleStats(issue.rule_id, issue.rule_name)).add(issue)

    if config is not None and not only:
        for issue in customrules.run(doc, config, policy):
            issues.append(issue)
            stats.setdefault(issue.rule_id,
                             RuleStats(issue.rule_id, issue.rule_name)).add(issue)

    if min_severity is not None:
        issues = [i for i in issues if i.severity.rank <= min_severity.rank]

    issues.sort(key=lambda i: (i.severity.rank, i.block_index if i.block_index >= 0 else 10 ** 6))

    return CheckResult(
        path=Path(path),
        doc=doc,
        issues=issues,
        stats=sorted(stats.values(), key=lambda s: -s.total),
        duration=time.perf_counter() - started,
        failed_rules=failed,
    )
