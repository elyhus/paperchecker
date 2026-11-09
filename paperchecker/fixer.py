# -*- coding: utf-8 -*-
"""一键修复：先预览差异，确认后写回，写回前自动备份原文件。"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Pt

from .docmodel import ParsedDoc
from .model import Issue


@dataclass
class FixChange:
    rule_id: str
    block_index: int
    field: str
    before: str
    after: str

    def as_row(self) -> str:
        return f"{self.rule_id}\t段{self.block_index}\t{self.field}\t{self.before} → {self.after}"


def preview(doc: ParsedDoc, issues: list[Issue]) -> list[FixChange]:
    """只计算“将要改什么”，不写文件。"""
    changes: list[FixChange] = []
    for issue in issues:
        if not issue.fixable:
            continue
        if issue.fix_kind == "font":
            changes.append(FixChange(issue.rule_id, issue.block_index, "字体",
                                     issue.actual, issue.expected))
        elif issue.fix_kind == "size":
            changes.append(FixChange(issue.rule_id, issue.block_index, "字号",
                                     issue.actual, issue.expected))
        elif issue.fix_kind == "spacing":
            changes.append(FixChange(issue.rule_id, issue.block_index, "行距",
                                     issue.actual, issue.expected))
        elif issue.fix_kind == "empty":
            for raw_index in issue.fix_payload.get("indexes", []):
                changes.append(FixChange(issue.rule_id, raw_index, "删除空段落", "存在", "已删除"))
    return changes


def backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.stem}.bak-{stamp}{path.suffix}")
    shutil.copy2(path, target)
    return target


def apply(path: str | Path, issues: list[Issue], policy_body_font: str = "宋体",
          policy_body_size: float = 12.0, policy_line: float = 20.0) -> tuple[Path, list[FixChange]]:
    from docx import Document
    from docx.text.paragraph import Paragraph

    path = Path(path)
    doc = Document(str(path))
    body = doc.element.body
    elements = list(body.iterchildren())

    def paragraph_at(index: int):
        if index < 0 or index >= len(elements):
            return None
        element = elements[index]
        if element.tag != qn("w:p"):
            return None
        return Paragraph(element, doc)

    changes: list[FixChange] = []
    for issue in issues:
        if not issue.fixable:
            continue
        para = paragraph_at(issue.block_index)
        if issue.fix_kind == "empty":
            targets = issue.fix_payload.get("indexes", [])
            for raw_index in sorted(targets, reverse=True):
                element = elements[raw_index] if raw_index < len(elements) else None
                if element is not None and element.tag == qn("w:p"):
                    body.remove(element)
                    changes.append(FixChange(issue.rule_id, raw_index, "删除空段落", "存在", "已删除"))
            continue
        if para is None:
            continue
        expect = issue.fix_payload.get("expect")       # 自定义规则可以自带期望值
        if issue.fix_kind == "font":
            target_font = str(expect) if expect else policy_body_font
            for run in para.runs:
                _set_font(run, target_font)
            changes.append(FixChange(issue.rule_id, issue.block_index, "字体", issue.actual, target_font))
        elif issue.fix_kind == "size":
            target_size = float(expect) if expect else policy_body_size
            for run in para.runs:
                run.font.size = Pt(target_size)
            changes.append(FixChange(issue.rule_id, issue.block_index, "字号",
                                     issue.actual, f"{target_size} 磅"))
        elif issue.fix_kind == "spacing":
            target_line = float(expect) if expect else policy_line
            fmt = para.paragraph_format
            fmt.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            fmt.line_spacing = Pt(target_line)
            changes.append(FixChange(issue.rule_id, issue.block_index, "行距",
                                     issue.actual, f"固定值 {target_line} 磅"))

    backup_path = backup(path)
    doc.save(str(path))
    return backup_path, changes


def _set_font(run, font_name: str) -> None:
    run.font.name = font_name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), font_name)
