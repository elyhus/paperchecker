# -*- coding: utf-8 -*-
"""规则库。

每条规则 = 一个纯函数：(ParsedDoc, Policy) -> list[Issue]。
规则只负责“发现问题”，不做任何写入，保证检查过程不修改原文件。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .docmodel import FIG_CAP_RE, TAB_CAP_RE, Block, ParsedDoc
from .model import Issue, Policy, Severity

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
ASCII_RE = re.compile(r"[A-Za-z0-9]")
REF_ITEM_RE = re.compile(r"^\s*(\[\d+\]|\d+[\.、])\s*\S")
CITE_RE = re.compile(r"\[\d+(?:[-,，]\s*\d+)*\]")
CN_HEAD_RE = re.compile(r"^第\s*([一二三四五六七八九十]+)\s*章")


@dataclass
class RuleDef:
    rule_id: str
    name: str
    severity: Severity
    check: Callable[[ParsedDoc, Policy], list[Issue]]
    fixable: bool = False


RULES: list[RuleDef] = []


def rule(rule_id: str, name: str, severity: Severity = Severity.ERROR, fixable: bool = False):
    def deco(fn):
        RULES.append(RuleDef(rule_id, name, severity, fn, fixable))
        return fn
    return deco


# ----------------------------- 公共工具 -----------------------------

def body_blocks(doc: ParsedDoc, policy: Policy) -> list[Block]:
    """正文段落：非标题、非题注、有足够长度（排除封面信息行）。"""
    out = []
    for block in doc.text_paragraphs:
        if block.is_heading:
            continue
        if FIG_CAP_RE.match(block.text.strip()) or TAB_CAP_RE.match(block.text.strip()):
            continue
        if len(block.text.strip()) < policy.body_min_chars:
            continue
        out.append(block)
    return out


def captions(doc: ParsedDoc) -> list[tuple[Block, str, int, int]]:
    out = []
    for block in doc.text_paragraphs:
        text = block.text.strip()
        match = FIG_CAP_RE.match(text)
        kind = "图"
        if not match:
            match = TAB_CAP_RE.match(text)
            kind = "表"
        if match:
            out.append((block, kind, int(match.group(1)), int(match.group(2))))
    return out


def _issue(rule_def: RuleDef, doc: ParsedDoc, block: Block | None, message: str,
           actual: str = "", expected: str = "", fix_kind: str | None = None,
           payload: dict | None = None) -> Issue:
    return Issue(
        rule_id=rule_def.rule_id,
        rule_name=rule_def.name,
        severity=rule_def.severity,
        message=message,
        location=doc.location(block) if block is not None else "全文",
        block_index=block.index if block is not None else -1,
        actual=actual,
        expected=expected,
        fixable=rule_def.fixable and fix_kind is not None,
        fix_kind=fix_kind,
        fix_payload=payload or {},
    )


def _run_font_problem(block: Block, expect_font: str) -> str | None:
    for run in block.runs:
        if not run.text.strip() or not CJK_RE.search(run.text):
            continue
        if run.font_east_asia is None:
            continue
        if run.font_east_asia != expect_font:
            return run.font_east_asia
    return None


def _run_size_problem(block: Block, expect_pt: float) -> float | None:
    for run in block.runs:
        if not run.text.strip():
            continue
        if run.size_pt is None:
            continue
        if abs(run.size_pt - expect_pt) > 0.05:
            return run.size_pt
    return None


# ----------------------------- 正文格式类 -----------------------------

@rule("R001", "正文字体应为宋体", fixable=True)
def check_body_font(doc, policy):
    issues = []
    for block in body_blocks(doc, policy):
        bad = _run_font_problem(block, policy.body_font)
        if bad:
            issues.append(_issue(ALL_RULES["R001"], doc, block,
                                 f"正文字体为“{bad}”，应为“{policy.body_font}”",
                                 actual=bad, expected=policy.body_font, fix_kind="font"))
    return issues


@rule("R002", "正文字号应为小四（12 磅）", fixable=True)
def check_body_size(doc, policy):
    issues = []
    for block in body_blocks(doc, policy):
        bad = _run_size_problem(block, policy.body_size_pt)
        if bad:
            issues.append(_issue(ALL_RULES["R002"], doc, block,
                                 f"正文字号为 {bad} 磅，应为 {policy.body_size_pt} 磅（小四）",
                                 actual=f"{bad} 磅", expected=f"{policy.body_size_pt} 磅", fix_kind="size"))
    return issues


@rule("R003", "正文行距应为固定值 20 磅", fixable=True)
def check_body_spacing(doc, policy):
    issues = []
    for block in body_blocks(doc, policy):
        ok = (block.line_rule == "固定值" and block.line_spacing_pt is not None
              and abs(block.line_spacing_pt - policy.body_line_pt) <= 0.05)
        if ok:
            continue
        if block.line_spacing_pt is None:
            actual = block.line_rule
        elif block.line_rule == "多倍行距":
            actual = f"{block.line_spacing_pt} 倍行距"
        else:
            actual = f"{block.line_spacing_pt} 磅（{block.line_rule}）"
        issues.append(_issue(ALL_RULES["R003"], doc, block,
                             f"行距为 {actual}，应为固定值 {policy.body_line_pt} 磅",
                             actual=actual, expected=f"固定值 {policy.body_line_pt} 磅", fix_kind="spacing"))
    return issues


@rule("R004", "标题层级不得跳级", Severity.WARN)
def check_heading_jump(doc, policy):
    issues = []
    prev = None
    for block in doc.headings:
        level = block.outline
        if prev is not None and level > prev + 1:
            issues.append(_issue(ALL_RULES["R004"], doc, block,
                                 f"标题由 {prev} 级直接跳到 {level} 级，缺少上级标题",
                                 actual=f"{prev} → {level}"))
        prev = level
    return issues


@rule("R005", "一级标题应另起一页", Severity.WARN)
def check_heading_page_break(doc, policy):
    issues = []
    content = [b for b in doc.blocks if b.text.strip()]
    first = content[0] if content else None
    front_matter = {"摘要", "目录", "Abstract", "英文摘要", "中文摘要"}
    for block in doc.headings:
        if block.outline != 1 or block is first:
            continue
        if block.text.strip().replace(" ", "").replace("\u3000", "") in front_matter:
            continue
        if not block.page_break_before:
            issues.append(_issue(ALL_RULES["R005"], doc, block,
                                 "一级标题未设置“段前分页”", actual="未分页", expected="段前分页"))
    return issues


@rule("R016", "标题序号与题目之间应空一格", Severity.INFO)
def check_heading_space(doc, policy):
    issues = []
    for block in doc.headings:
        text = block.text.strip()
        if re.match(r"^\d+(\.\d+)*[\u4e00-\u9fff]", text):
            issues.append(_issue(ALL_RULES["R016"], doc, block,
                                 "标题序号后缺少空格，如“1.1 研究现状”",
                                 actual=text[:16], expected="序号 + 空格 + 题目"))
    return issues


@rule("R018", "章标题序号应使用阿拉伯数字", Severity.WARN)
def check_cn_chapter(doc, policy):
    issues = []
    for block in doc.headings:
        if block.outline == 1 and CN_HEAD_RE.match(block.text.strip()):
            issues.append(_issue(ALL_RULES["R018"], doc, block,
                                 "章标题使用了中文数字序号，应改为阿拉伯数字（如“第2章”）",
                                 actual=block.text.strip()[:16], expected="第N章 …"))
    return issues


# ----------------------------- 结构与内容类 -----------------------------

@rule("R006", "摘要字数应在 200–300 字")
def check_abstract_length(doc, policy):
    text, start = doc.section_text(("摘要", "摘　要"), ("关键词", "关键字", "Abstract", "abstract"))
    if not text:
        return []
    count = len(re.sub(r"\s", "", text))
    low, high = policy.abstract_range
    if not (low <= count <= high):
        block = next((b for b in doc.blocks if b.index == start), None)
        return [_issue(ALL_RULES["R006"], doc, block,
                       f"摘要正文 {count} 字，应在 {low}–{high} 字之间",
                       actual=f"{count} 字", expected=f"{low}–{high} 字")]
    return []


@rule("R017", "摘要中不得出现参考文献引用")
def check_abstract_citation(doc, policy):
    text, start = doc.section_text(("摘要", "摘　要"), ("关键词", "关键字", "Abstract", "abstract"))
    hits = CITE_RE.findall(text or "")
    if hits:
        block = next((b for b in doc.blocks if b.index == start), None)
        return [_issue(ALL_RULES["R017"], doc, block,
                       f"摘要中出现文献引用 {hits[0]}，摘要不标注引用",
                       actual=hits[0], expected="无引用")]
    return []


@rule("R007", "关键词应为 3–5 个，用中文逗号分隔")
def check_keywords(doc, policy):
    for block in doc.text_paragraphs:
        text = block.text.strip()
        if not re.match(r"^关\s*键\s*词\s*[:：]", text):
            continue
        raw = re.sub(r"^关\s*键\s*词\s*[:：]", "", text)
        parts = [p for p in re.split(r"[，,、;；]", raw) if p.strip()]
        low, high = policy.keyword_range
        if not (low <= len(parts) <= high):
            return [_issue(ALL_RULES["R007"], doc, block,
                           f"关键词 {len(parts)} 个（{'、'.join(parts)}），应为 {low}–{high} 个",
                           actual=f"{len(parts)} 个", expected=f"{low}–{high} 个")]
    return []


@rule("R008", "目录应由 Word 自动生成", Severity.WARN)
def check_toc(doc, policy):
    if doc.has_toc_field():
        return []
    return [Issue(rule_id="R008", rule_name="目录应由 Word 自动生成", severity=Severity.WARN,
                  message="未检测到目录域，目录不是自动生成的（手工目录无法随正文更新）",
                  location="全文", actual="无 TOC 域", expected="插入 → 引用 → 目录")]


@rule("R009", "图表编号应按章连续编号")
def check_caption_numbering(doc, policy):
    issues = []
    last: dict[tuple[str, int], int] = {}
    for block, kind, chapter, number in captions(doc):
        key = (kind, chapter)
        expect = last.get(key, 0) + 1
        if number != expect:
            issues.append(_issue(ALL_RULES["R009"], doc, block,
                                 f"{kind}{chapter}-{number} 编号不连续，此处应为 {kind}{chapter}-{expect}",
                                 actual=f"{kind}{chapter}-{number}", expected=f"{kind}{chapter}-{expect}"))
        last[key] = max(number, last.get(key, 0))
    return issues


@rule("R010", "图表题注应为黑体五号")
def check_caption_style(doc, policy):
    issues = []
    for block, kind, _c, _n in captions(doc):
        font = _run_font_problem(block, policy.caption_font) or None
        size = _run_size_problem(block, policy.caption_size_pt)
        if font or size:
            issues.append(_issue(ALL_RULES["R010"], doc, block,
                                 f"{kind}题注格式为 {font or '字体正确'}/{size or policy.caption_size_pt} 磅，"
                                 f"应为 {policy.caption_font} 五号",
                                 actual=f"{font or policy.caption_font} / {size or policy.caption_size_pt} 磅",
                                 expected=f"{policy.caption_font} / {policy.caption_size_pt} 磅"))
    return issues


@rule("R011", "结论字数应在 400–1000 字")
def check_conclusion(doc, policy):
    text, start = doc.section_text(("结论", "结　论", "结束语"), ("致谢", "致　谢", "参考文献"))
    if not text:
        return []
    count = len(re.sub(r"\s", "", text))
    low, high = policy.conclusion_range
    if not (low <= count <= high):
        block = next((b for b in doc.blocks if b.index == start), None)
        return [_issue(ALL_RULES["R011"], doc, block,
                       f"结论 {count} 字，应在 {low}–{high} 字之间",
                       actual=f"{count} 字", expected=f"{low}–{high} 字")]
    return []


@rule("R012", "参考文献不少于 10 篇")
def check_ref_count(doc, policy):
    refs = _refs(doc)
    if not refs:
        return [Issue(rule_id="R012", rule_name="参考文献不少于 10 篇", severity=Severity.ERROR,
                      message="未找到参考文献条目", location="全文",
                      actual="0 篇", expected=f"≥{policy.min_refs} 篇")]
    if len(refs) < policy.min_refs:
        block = refs[0][0]
        return [_issue(ALL_RULES["R012"], doc, block,
                       f"参考文献 {len(refs)} 篇，应不少于 {policy.min_refs} 篇",
                       actual=f"{len(refs)} 篇", expected=f"≥{policy.min_refs} 篇")]
    return []


@rule("R013", "英文文献不少于 2 篇")
def check_ref_en(doc, policy):
    refs = _refs(doc)
    en = [r for r in refs if _is_english_ref(r[1])]
    if len(en) < policy.min_en_refs:
        block = refs[0][0] if refs else None
        return [_issue(ALL_RULES["R013"], doc, block,
                       f"英文文献 {len(en)} 篇，应不少于 {policy.min_en_refs} 篇",
                       actual=f"{len(en)} 篇", expected=f"≥{policy.min_en_refs} 篇")]
    return []


@rule("R014", "数字与字母应使用 Times New Roman", Severity.WARN)
def check_latin_font(doc, policy):
    issues = []
    for block in body_blocks(doc, policy):
        for run in block.runs:
            # 只判断“纯英文/数字片段”：混合 run 的字符级字体需拆 run 才能精确判定，
            # 这里保守处理，避免对中文正文大量误报。
            if len(ASCII_RE.findall(run.text)) < 5 or CJK_RE.search(run.text):
                continue
            if run.font_ascii and run.font_ascii != policy.latin_font:
                issues.append(_issue(ALL_RULES["R014"], doc, block,
                                     f"英文/数字字体为“{run.font_ascii}”，应为 {policy.latin_font}",
                                     actual=run.font_ascii, expected=policy.latin_font))
                break
    return issues


@rule("R015", "不得出现连续 3 个以上空段落", Severity.WARN, fixable=True)
def check_empty_paragraphs(doc, policy):
    issues = []
    streak: list[Block] = []
    for block in doc.blocks:
        if block.kind == "p" and not block.text.strip():
            streak.append(block)
            continue
        if len(streak) >= 3:
            issues.append(_issue(ALL_RULES["R015"], doc, streak[0],
                                 f"连续 {len(streak)} 个空段落，应删除或改为段落间距",
                                 actual=f"{len(streak)} 个", expected="≤2 个",
                                 fix_kind="empty", payload={"indexes": [b.index for b in streak[2:]]}))
        streak = []
    return issues


def _refs(doc: ParsedDoc):
    """返回参考文献条目 [(block, text)]。"""
    in_refs = False
    out = []
    for block in doc.text_paragraphs:
        text = block.text.strip()
        head = text.replace(" ", "")
        if head.startswith("参考文献"):
            in_refs = True
            continue
        if not in_refs:
            continue
        if block.is_heading and block.outline == 1:
            break
        if REF_ITEM_RE.match(text):
            out.append((block, text))
    return out


def _is_english_ref(text: str) -> bool:
    letters = len(re.findall(r"[A-Za-z]", text))
    cjk = len(CJK_RE.findall(text))
    return letters >= 20 and cjk <= 4


ALL_RULES: dict[str, RuleDef] = {r.rule_id: r for r in RULES}
