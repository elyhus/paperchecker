# -*- coding: utf-8 -*-
"""用户自定义规则：声明式配置 + 通用执行器。

设计目标：**不改代码就能加规则**。一条规则 = 范围(scope) + 条件(type/pattern/expect) + 提示语。

四种规则类型：
    text    文本检查      pattern 正则；mode=forbid 命中即报，mode=require 必须出现
    format  格式检查      prop=font|size|line_spacing，expect 期望值
    length  字数检查      section 小节名；min/max
    count   数量检查      target=references|english_references|keywords；min/max

配置文件默认在 rules/custom_rules.json，可随项目分发，也可每人一份。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import rules as builtin
from .docmodel import FIG_CAP_RE, TAB_CAP_RE, Block, ParsedDoc
from .model import Issue, Policy, Severity

SCOPES = {
    "body": "正文段落",
    "heading": "各级标题",
    "caption": "图表题注",
    "reference": "参考文献",
    "all": "全部段落",
    "section": "指定小节",
}

PROPS = {
    "font": "字体",
    "size": "字号（磅）",
    "line_spacing": "行距（磅）",
}

TARGETS = {
    "references": "参考文献篇数",
    "english_references": "英文文献篇数",
    "keywords": "关键词个数",
}

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "rules" / "custom_rules.json"


@dataclass
class CustomRule:
    id: str
    name: str
    type: str = "text"
    scope: str = "body"
    severity: Severity = Severity.WARN
    enabled: bool = True
    message: str = ""
    # text
    pattern: str = ""
    mode: str = "forbid"          # forbid / require
    # format
    prop: str = "font"
    expect: Any = None
    # length / count
    section: str = ""
    target: str = ""
    min: float | None = None
    max: float | None = None
    fixable: bool = False

    def __post_init__(self) -> None:
        self.severity = _severity(self.severity)      # 允许直接传 "警告" 这样的字符串

    def to_dict(self) -> dict:
        data = {"id": self.id, "name": self.name, "type": self.type, "scope": self.scope,
                "severity": self.severity.value, "enabled": self.enabled, "message": self.message}
        if self.type == "text":
            data.update(pattern=self.pattern, mode=self.mode)
        elif self.type == "format":
            data.update(prop=self.prop, expect=self.expect)
        elif self.type == "length":
            data.update(section=self.section, min=self.min, max=self.max)
        elif self.type == "count":
            data.update(target=self.target, min=self.min, max=self.max)
        if self.section:                      # text 规则也可能限定在某个小节
            data["section"] = self.section
        return {k: v for k, v in data.items() if v not in ("", None)}

    @staticmethod
    def from_dict(data: dict) -> "CustomRule":
        return CustomRule(
            id=str(data.get("id", "")),
            name=str(data.get("name", "未命名规则")),
            type=data.get("type", "text"),
            scope=data.get("scope", "body"),
            severity=_severity(data.get("severity")),
            enabled=bool(data.get("enabled", True)),
            message=str(data.get("message", "")),
            pattern=data.get("pattern", ""),
            mode=data.get("mode", "forbid"),
            prop=data.get("prop", "font"),
            expect=data.get("expect"),
            section=data.get("section", ""),
            target=data.get("target", ""),
            min=data.get("min"),
            max=data.get("max"),
        )


@dataclass
class RuleConfig:
    path: Path
    params: dict = field(default_factory=dict)
    rules: list[CustomRule] = field(default_factory=list)

    def policy(self) -> Policy:
        """把配置里的参数覆盖到默认 Policy 上。"""
        base = Policy()
        for key, value in (self.params or {}).items():
            if not hasattr(base, key):
                continue
            if key.endswith("_range") and isinstance(value, list) and len(value) == 2:
                value = (float(value[0]), float(value[1]))
            setattr(base, key, value)
        return base

    def save(self) -> None:
        payload = {
            "version": 1,
            "_说明": "scope: body/heading/caption/reference/all/section；"
                    "type: text/format/length/count；severity: 错误/警告/提示",
            "params": self.params,
            "rules": [rule.to_dict() for rule in self.rules],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _severity(value) -> Severity:
    if isinstance(value, Severity):
        return value
    return {"错误": Severity.ERROR, "警告": Severity.WARN, "提示": Severity.INFO}.get(str(value), Severity.WARN)


DEFAULT_RULES = [
    {
        "id": "C001",
        "name": "正文不得出现口语化表述",
        "type": "text",
        "scope": "body",
        "mode": "forbid",
        "pattern": "笔者认为|我认为|我觉得|众所周知",
        "severity": "警告",
        "message": "正文出现口语化表述：{match}",
    },
    {
        "id": "C002",
        "name": "摘要需说明研究方法",
        "type": "text",
        "scope": "section",
        "section": "摘要",
        "mode": "require",
        "pattern": "方法|算法|模型|框架|设计",
        "severity": "提示",
        "message": "摘要中未见对研究方法/技术路线的说明",
    },
    {
        "id": "C003",
        "name": "参考文献需标注文献类型",
        "type": "text",
        "scope": "reference",
        "mode": "require",
        "pattern": r"\[(J|M|D|C|N|R|S|P|EB/OL)\]",
        "severity": "警告",
        "message": "参考文献缺少文献类型标识（如 [J]/[M]/[D]）",
    },
]


def load(path: str | Path | None = None) -> RuleConfig:
    """读取配置；文件不存在时写入一份示例，方便用户照着改。"""
    target = Path(path) if path else DEFAULT_PATH
    if not target.exists():
        config = RuleConfig(path=target, params={},
                            rules=[CustomRule.from_dict(r) for r in DEFAULT_RULES])
        config.save()
        return config
    data = json.loads(target.read_text(encoding="utf-8"))
    return RuleConfig(
        path=target,
        params=data.get("params", {}),
        rules=[CustomRule.from_dict(item) for item in data.get("rules", [])],
    )


# ----------------------------- 执行 -----------------------------

def run(doc: ParsedDoc, config: RuleConfig, policy: Policy) -> list[Issue]:
    issues: list[Issue] = []
    for rule in config.rules:
        if not rule.enabled:
            continue
        try:
            issues.extend(_run_one(doc, rule, policy))
        except re.error as exc:
            issues.append(_issue(rule, doc, None, f"规则的正则表达式有误：{exc}"))
        except Exception as exc:                     # 单条自定义规则出错不影响其他规则
            issues.append(_issue(rule, doc, None, f"规则执行异常：{exc}"))
    return issues


def _run_one(doc: ParsedDoc, rule: CustomRule, policy: Policy) -> list[Issue]:
    if rule.type == "text":
        return _check_text(doc, rule, policy)
    if rule.type == "format":
        return _check_format(doc, rule, policy)
    if rule.type == "length":
        return _check_length(doc, rule)
    if rule.type == "count":
        return _check_count(doc, rule, policy)
    return [_issue(rule, doc, None, f"未知的规则类型：{rule.type}")]


def _blocks(doc: ParsedDoc, scope: str, policy: Policy, rule: CustomRule) -> list[Block]:
    if scope == "body":
        return builtin.body_blocks(doc, policy)
    if scope == "heading":
        return list(doc.headings)
    if scope == "caption":
        return [block for block, *_ in builtin.captions(doc)]
    if scope == "reference":
        return [block for block, _ in builtin._refs(doc)]
    if scope == "section":
        return _section_blocks(doc, rule.section)
    return list(doc.text_paragraphs)


def _section_blocks(doc: ParsedDoc, title: str) -> list[Block]:
    """取某个标题（如“摘要”）到下一个标题之间的段落。"""
    if not title:
        return []
    blocks: list[Block] = []
    inside = False
    level = None
    for block in doc.text_paragraphs:
        head = block.text.strip().replace(" ", "").replace("\u3000", "")
        if not inside and head.startswith(title):
            inside = True
            level = block.outline or 1
            continue
        if inside:
            if block.is_heading and (block.outline or 1) <= (level or 1):
                break
            blocks.append(block)
    return blocks


def _check_text(doc: ParsedDoc, rule: CustomRule, policy: Policy) -> list[Issue]:
    if not rule.pattern:
        return [_issue(rule, doc, None, "规则缺少 pattern")]
    if rule.scope == "section" and not rule.section:
        return [_issue(rule, doc, None, "范围是“指定小节”，但没有填写小节名称")]
    regex = re.compile(rule.pattern)
    targets = _blocks(doc, rule.scope, policy, rule)
    if rule.mode == "require":
        joined = "\n".join(block.text for block in targets)
        if not regex.search(joined):
            scope_name = SCOPES.get(rule.scope, rule.scope)
            return [_issue(rule, doc, targets[0] if targets else None,
                           rule.message or f"{scope_name}未匹配到 /{rule.pattern}/")]
        return []

    issues = []
    for block in targets:
        match = regex.search(block.text)
        if match:
            message = (rule.message or "命中禁止内容：{match}").replace("{match}", match.group(0))
            issues.append(_issue(rule, doc, block, message,
                                 actual=match.group(0), expected="不应出现"))
    return issues


def _check_format(doc: ParsedDoc, rule: CustomRule, policy: Policy) -> list[Issue]:
    issues = []
    for block in _blocks(doc, rule.scope, policy, rule):
        actual, ok = _read_prop(block, rule.prop, rule.expect)
        if ok:
            continue
        fix_kind = {"font": "font", "size": "size", "line_spacing": "spacing"}.get(rule.prop)
        issues.append(_issue(rule, doc, block,
                             rule.message or f"{PROPS.get(rule.prop, rule.prop)}为 {actual}，应为 {rule.expect}",
                             actual=str(actual), expected=str(rule.expect),
                             fix_kind=fix_kind, fixable=fix_kind is not None,
                             payload={"expect": rule.expect}))
    return issues


def _read_prop(block: Block, prop: str, expect) -> tuple[Any, bool]:
    if prop == "font":
        for run in block.runs:
            if run.text.strip() and run.font_east_asia:
                return run.font_east_asia, run.font_east_asia == expect
        return "未设置", False
    if prop == "size":
        for run in block.runs:
            if run.text.strip() and run.size_pt:
                return f"{run.size_pt} 磅", abs(run.size_pt - float(expect)) <= 0.05
        return "未设置", False
    if prop == "line_spacing":
        if block.line_spacing_pt is None:
            return block.line_rule, False
        return f"{block.line_spacing_pt} 磅", (
            block.line_rule == "固定值" and abs(block.line_spacing_pt - float(expect)) <= 0.05)
    return "未知属性", False


def _check_length(doc: ParsedDoc, rule: CustomRule) -> list[Issue]:
    text, start = doc.section_text((rule.section,), ("关键词", "关键字", "Abstract"))
    if not text:
        return [_issue(rule, doc, None, f"未找到小节「{rule.section}」")]
    count = len(re.sub(r"\s", "", text))
    low, high = rule.min, rule.max
    bad = (low is not None and count < low) or (high is not None and count > high)
    if not bad:
        return []
    block = next((b for b in doc.blocks if b.index == start), None)
    expect = f"{int(low) if low else 0}–{int(high) if high else '∞'} 字"
    return [_issue(rule, doc, block,
                   rule.message or f"「{rule.section}」{count} 字，应为 {expect}",
                   actual=f"{count} 字", expected=expect)]


def _check_count(doc: ParsedDoc, rule: CustomRule, policy: Policy) -> list[Issue]:
    if rule.target in ("references", "english_references"):
        refs = builtin._refs(doc)
        value = len(refs) if rule.target == "references" else \
            len([r for r in refs if builtin._is_english_ref(r[1])])
        anchor = refs[0][0] if refs else None
    elif rule.target == "keywords":
        value = 0
        anchor = None
        for block in doc.text_paragraphs:
            if re.match(r"^关\s*键\s*词\s*[:：]", block.text.strip()):
                raw = re.sub(r"^关\s*键\s*词\s*[:：]", "", block.text.strip())
                value = len([p for p in re.split(r"[，,、;；]", raw) if p.strip()])
                anchor = block
                break
    else:
        return [_issue(rule, doc, None, f"未知的统计对象：{rule.target}")]

    low, high = rule.min, rule.max
    bad = (low is not None and value < low) or (high is not None and value > high)
    if not bad:
        return []
    expect = f"{int(low) if low is not None else 0}–{int(high) if high is not None else '∞'}"
    return [_issue(rule, doc, anchor,
                   rule.message or f"{TARGETS.get(rule.target, rule.target)}为 {value}，应为 {expect}",
                   actual=str(value), expected=expect)]


def _issue(rule: CustomRule, doc: ParsedDoc, block: Block | None, message: str,
           actual: str = "", expected: str = "", fix_kind: str | None = None,
           fixable: bool = False, payload: dict | None = None) -> Issue:
    return Issue(
        rule_id=rule.id,
        rule_name=rule.name,
        severity=rule.severity,
        message=message,
        location=doc.location(block) if block is not None else "全文",
        block_index=block.index if block is not None else -1,
        actual=actual,
        expected=expected,
        fixable=bool(fixable and fix_kind),
        fix_kind=fix_kind,
        fix_payload=payload or {},
    )
