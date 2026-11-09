# -*- coding: utf-8 -*-
"""docx 解析：把文档变成带“实际生效格式”的块序列。

难点在于 docx 的格式是三层叠加的：直接格式（pPr/rPr）> 样式链（style → base_style）
> 文档默认（docDefaults）。只看 paragraph_format 会漏掉"样式里定义的宋体小四"，
因此这里统一走样式链回溯，并在 Issue 里区分“来自直接格式”还是“来自样式”。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Length

HEADING_STYLE_RE = re.compile(r"^(?:heading|标题)\s*(\d)", re.I)
CN_CHAPTER_RE = re.compile(r"^第\s*[0-9一二三四五六七八九十百]+\s*章")
NUM_HEAD_RE = re.compile(r"^(\d+(?:\.\d+){0,3})[\s\u3000、.．]")
FIG_CAP_RE = re.compile(r"^图\s*(\d+)\s*[-‑–—.]\s*(\d+)")
TAB_CAP_RE = re.compile(r"^表\s*(\d+)\s*[-‑–—.]\s*(\d+)")

TOC_LINE_RE = re.compile(r"(\.{4,}|…{2,}|·{4,})\s*\d+\s*$")


def norm_heading(text: str) -> str:
    """去掉半角/全角空格，便于比对“摘 要 / 摘　要 / 摘要”。"""
    return text.strip().replace(" ", "").replace("\u3000", "")


SPECIAL_HEADS = {
    "摘要": 1, "摘　要": 1, "中文摘要": 1,
    "abstract": 1, "英文摘要": 1,
    "目录": 1, "目　录": 1,
    "结论": 1, "结　论": 1, "结束语": 1,
    "致谢": 1, "致　谢": 1,
    "参考文献": 1, "附　录": 1, "附录": 1,
}


def _pt(value):
    if value is None:
        return None
    if isinstance(value, Length):
        return round(value.pt, 1)
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _spacing_value(value):
    """line_spacing 可能是 Length（固定值）或倍数（float）。"""
    if value is None:
        return None
    if isinstance(value, Length):
        return round(value.pt, 1)
    return round(float(value), 2)


def _rule_of(paragraph_or_style):
    fmt = paragraph_or_style.paragraph_format
    try:
        return fmt.line_spacing_rule
    except Exception:
        return None


@dataclass
class RunInfo:
    text: str
    font_ascii: str | None
    font_east_asia: str | None
    size_pt: float | None
    bold: bool


@dataclass
class Block:
    index: int
    kind: str                      # p / tbl
    text: str
    style: str
    outline: int | None
    line_spacing_pt: float | None
    line_rule: str
    space_before_pt: float | None
    space_after_pt: float | None
    first_line_indent_pt: float | None
    page_break_before: bool
    runs: list[RunInfo] = field(default_factory=list)
    chapter: int = 0
    section: str = ""          # 前置/篇末的特殊标题：摘要、目录、结论、参考文献…

    @property
    def is_heading(self) -> bool:
        return self.outline is not None

    @property
    def short(self) -> str:
        text = self.text.strip().replace("\n", " ")
        return text if len(text) <= 28 else text[:28] + "…"


class ParsedDoc:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.doc = Document(str(self.path))
        self.blocks: list[Block] = []
        self._parse()
        self._mark_chapters()

    # ---------- 解析 ----------

    def _parse(self) -> None:
        body = self.doc.element.body
        idx = 0
        for child in body.iterchildren():
            tag = child.tag.split("}")[-1]
            if tag == "p":
                self.blocks.append(self._parse_paragraph(child, idx))
            elif tag == "tbl":
                self.blocks.append(Block(
                    index=idx, kind="tbl", text="", style="Table", outline=None,
                    line_spacing_pt=None, line_rule="", space_before_pt=None,
                    space_after_pt=None, first_line_indent_pt=None,
                    page_break_before=False,
                ))
            idx += 1

    def _parse_paragraph(self, element, idx: int) -> Block:
        from docx.text.paragraph import Paragraph

        para = Paragraph(element, self.doc)
        style_name = para.style.name if para.style is not None else "Normal"
        text = para.text
        outline = self._guess_outline(para, style_name, text)

        ls, rule = self._line_spacing(para)
        return Block(
            index=idx,
            kind="p",
            text=text,
            style=style_name,
            outline=outline,
            line_spacing_pt=ls,
            line_rule=rule,
            space_before_pt=_pt(self._inherit(para, lambda f: f.space_before)),
            space_after_pt=_pt(self._inherit(para, lambda f: f.space_after)),
            first_line_indent_pt=_pt(self._inherit(para, lambda f: f.first_line_indent)),
            page_break_before=bool(para.paragraph_format.page_break_before),
            runs=[self._run_info(r) for r in para.runs],
        )

    def _run_info(self, run) -> RunInfo:
        east = None
        rpr = run._element.rPr
        if rpr is not None and rpr.rFonts is not None:
            east = rpr.rFonts.get(qn("w:eastAsia"))
        if east is None:
            east = self._style_east_asia(run)
        size = run.font.size
        if size is None:
            size = self._style_size(run)
        return RunInfo(
            text=run.text,
            font_ascii=run.font.name,
            font_east_asia=east,
            size_pt=round(size.pt, 1) if size is not None else None,
            bold=bool(run.bold),
        )

    # ---------- 格式回溯 ----------

    @staticmethod
    def _inherit(para, getter):
        value = getter(para.paragraph_format)
        if value is not None:
            return value
        style = para.style
        while style is not None:
            value = getter(style.paragraph_format)
            if value is not None:
                return value
            style = style.base_style
        return None

    def _line_spacing(self, para):
        if para.paragraph_format.line_spacing is not None:
            rule = para.paragraph_format.line_spacing_rule
            return _spacing_value(para.paragraph_format.line_spacing), _rule_name(rule)
        style = para.style
        while style is not None:
            fmt = style.paragraph_format
            if fmt.line_spacing is not None:
                return _spacing_value(fmt.line_spacing), _rule_name(fmt.line_spacing_rule)
            style = style.base_style
        return None, "未设置"

    @staticmethod
    def _style_chain(run_or_para):
        style = getattr(run_or_para, "style", None)
        while style is not None:
            yield style
            style = style.base_style

    def _style_east_asia(self, run):
        for style in self._style_chain_from_run(run):
            element = style.element
            rpr = element.rPr
            if rpr is not None and rpr.rFonts is not None:
                value = rpr.rFonts.get(qn("w:eastAsia"))
                if value:
                    return value
        return None

    @staticmethod
    def _style_chain_from_run(run):
        para = getattr(run, "_parent", None)          # run 的父对象就是 Paragraph
        style = para.style if para is not None else None
        chain = []
        while style is not None:
            chain.append(style)
            style = style.base_style
        return chain

    @staticmethod
    def _style_size(run):
        for style in ParsedDoc._style_chain_from_run(run):
            if style.font.size is not None:
                return style.font.size
        return None

    # ---------- 标题与章节 ----------

    @staticmethod
    def _guess_outline(para, style_name: str, text: str) -> int | None:
        match = HEADING_STYLE_RE.match(style_name or "")
        if match:
            return int(match.group(1))
        stripped = text.strip()
        if not stripped or len(stripped) > 40:
            return None
        if TOC_LINE_RE.search(stripped):        # 目录条目（带前导点与页码）不是标题
            return None
        if norm_heading(stripped).lower() in SPECIAL_HEADS:
            return SPECIAL_HEADS[norm_heading(stripped).lower()]
        if CN_CHAPTER_RE.match(stripped):
            return 1
        if stripped.endswith(("。", "；", "，", "：")):
            return None
        num = NUM_HEAD_RE.match(stripped)
        if num:
            return num.group(1).count(".") + 1
        return None

    def _mark_chapters(self) -> None:
        chapter = 0
        for block in self.blocks:
            text = block.text.strip()
            if block.outline == 1 and norm_heading(text).lower() in SPECIAL_HEADS:
                block.section = norm_heading(text)
                block.chapter = chapter
                continue
            if block.outline == 1:
                match = CN_CHAPTER_RE.match(text)
                if match:
                    chapter = _cn_to_int(text)
                elif re.match(r"^\d+(\.\d+)?\s*\S", text):
                    chapter = int(re.match(r"^(\d+)", text).group(1))
            block.chapter = chapter

    # ---------- 便捷访问 ----------

    @property
    def paragraphs(self) -> list[Block]:
        return [b for b in self.blocks if b.kind == "p"]

    @property
    def text_paragraphs(self) -> list[Block]:
        return [b for b in self.paragraphs if b.text.strip()]

    @property
    def headings(self) -> list[Block]:
        return [b for b in self.text_paragraphs if b.is_heading]

    def section_text(self, titles: tuple[str, ...], stop_at: tuple[str, ...]) -> tuple[str, int]:
        """取某个小节下的正文文本，返回 (文本, 起始块号)。"""
        start = None
        for block in self.text_paragraphs:
            head = block.text.strip().replace(" ", "")
            if any(head.startswith(t) for t in titles):
                start = block.index
                break
        if start is None:
            return "", -1
        buffer = []
        for block in self.blocks:
            if block.index <= start:
                continue
            text = block.text.strip()
            if not text:
                continue
            head = text.replace(" ", "")
            if any(head.startswith(s) for s in stop_at):
                break
            buffer.append(text)
        return "\n".join(buffer), start

    def has_toc_field(self) -> bool:
        xml = self.doc.element.body.xml
        return "TOC \\o" in xml or "TOC\\o" in xml or 'instrText' in xml and "TOC" in xml

    def location(self, block: Block) -> str:
        if block.section:
            scope = block.section
        elif block.chapter:
            scope = f"第{block.chapter}章"
        else:
            scope = "前置部分"
        return f"{scope} · 段{block.index}「{block.short}」"


def _rule_name(rule) -> str:
    if rule == WD_LINE_SPACING.EXACTLY:
        return "固定值"
    if rule == WD_LINE_SPACING.ONE_POINT_FIVE:
        return "1.5 倍行距"
    if rule == WD_LINE_SPACING.AT_LEAST:
        return "最小值"
    if rule == WD_LINE_SPACING.MULTIPLE:
        return "多倍行距"
    if rule == WD_LINE_SPACING.SINGLE:
        return "单倍行距"
    if rule == WD_LINE_SPACING.DOUBLE:
        return "双倍行距"
    return "未设置"


CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_to_int(text: str) -> int:
    match = re.search(r"第\s*([0-9一二三四五六七八九十百]+)\s*章", text)
    if not match:
        return 0
    token = match.group(1)
    if token.isdigit():
        return int(token)
    if token == "十":
        return 10
    if token.startswith("十"):
        return 10 + CN_DIGITS.get(token[1:], 0)
    if "十" in token:
        tens, _, ones = token.partition("十")
        return CN_DIGITS.get(tens, 0) * 10 + CN_DIGITS.get(ones, 0)
    return CN_DIGITS.get(token, 0)
