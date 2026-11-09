# -*- coding: utf-8 -*-
"""在【副本】上填写"专业实训选题单"（A 题：文档格式合规检查智能体）。

原模板文件不做任何修改：本脚本只读取模板，另存为带"【新】"前缀的新文件。
格式约束（来自模板书写说明）：宋体 5 号、行距固定值 20、不得改动表格结构与列宽。
每个单元格的行高是"固定值"，写入后若行数超出会被裁切，因此正文按可用行数严格控制。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Pt

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "2023级专业综合实训选题单.docx"
DST = ROOT / "【新】2023级专业综合实训选题单-A题填写稿.docx"

FONT = "宋体"
SIZE = Pt(10.5)          # 5 号
LINE = Pt(20)            # 固定值 20 磅
CHARS_PER_LINE = 44      # 17cm 正文宽度 / 10.5pt 汉字，保守估计

TITLE = "面向高校文档规范的桌面智能体设计与实现——格式检查、自动修复与批处理"

SEC1 = (
    "高校课程报告、实训报告与毕业设计说明书均有严格的排版规范，涉及字体字号、行距、标题层级、"
    "图表编号与参考文献著录等数十项要求。学生目前只能人工逐条核对，耗时且易遗漏，教师亦需大量"
    "时间做格式初审。本设计将格式审查转化为可执行规则与可解释报告，以降低返工率、提升初审效率。"
    "docx 存在样式继承与直接格式交织，段落级格式判定具有技术难度；结合大模型做语义检查，"
    "是“规则引擎+大模型”混合架构的工程实践。"
)

SEC2 = [
    "（1）解析 docx 的段落格式、样式继承链与节属性，建立可定位的文档结构模型；",
    "（2）内置可配置规则库，覆盖字体、字号、行距、标题、图表、文献等不少于18条规则；",
    "（3）输出含位置、现状值、期望值、严重级别的问题清单，并支持跳转定位；",
    "（4）可修复项一键修复，修复前生成差异预览与原文件备份，支持回滚；",
    "（5）30页文档检查不超过10秒，人工标注样本上误报率不高于5%。",
]

SEC3 = [
    "（1）文档解析模块：解包、段落与字符格式提取、样式继承解析、表格与题注识别；",
    "（2）规则引擎模块：规则描述模型、规则加载校验、执行器与结果聚合去重；",
    "（3）语义检查模块：摘要与文献抽取、提示词构造、结构化输出约束与失败降级；",
    "（4）修复模块：规则与修复动作映射、差异预览、原文件备份与回滚；",
    "（5）可视化模块：问题列表、按规则与级别统计图表、检查报告导出；",
    "（6）数据管理模块：SQLite 存储规则、任务、问题、修复记录与模型配置，密钥加密存储。",
]

SEC4 = [
    "系统采用三层架构：表现层负责文件导入、问题列表与修复预览；应用层由文档解析器、规则引擎、"
    "语义检查服务与修复服务组成；数据层使用 SQLite 与本地文件系统。",
    "模型调用经统一的 Provider 适配层封装，支持多家厂商并允许用户自填 API Key，密钥以系统密钥链"
    "加密保存，请求直连厂商而不经过自建中转，以规避成本与数据合规风险。",
    "关键技术包括 python-docx 与 OOXML 直接操作、样式继承链解析、JSON Schema 约束模型结构化输出、"
    "异步任务与进度反馈、修复前快照回滚。",
    "数据模型包含模型配置、规则库、检查任务、问题明细、修复记录与语义检查结果六张表，其 E-R 关系"
    "与字段设计在第3章给出。",
    "测试方案：构造20份含已知违规的样本文档，统计检出率、误报率与修复成功率。主要风险是样式继承"
    "导致实际格式难以判定，对策为分级降级并对不确定项标注“需人工确认”。",
]


def style_run(run) -> None:
    run.font.name = FONT
    run.font.size = SIZE
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), FONT)


def style_para(paragraph, indent: bool = False) -> None:
    pf = paragraph.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = LINE
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    if indent:
        pf.first_line_indent = Pt(21)


def unique_cells(row):
    out, seen = [], set()
    for cell in row.cells:
        if id(cell._tc) in seen:
            continue
        seen.add(id(cell._tc))
        out.append(cell)
    return out


def set_cell_text(cell, text: str) -> None:
    """清空单元格并写入文本，保留单元格宽度与段落格式。"""
    paragraph = cell.paragraphs[0]
    for run in list(paragraph.runs):
        run._element.getparent().remove(run._element)
    run = paragraph.add_run(text)
    style_run(run)
    style_para(paragraph)


def fill_block(cell, lines) -> int:
    """把内容逐行写入单元格内已存在的空段落，返回占用的行数。"""
    paragraphs = cell.paragraphs[1:]          # 第 0 段是"一、目的和意义"标题
    used = 0
    for idx, text in enumerate(lines):
        if idx >= len(paragraphs):
            raise ValueError("空段落不足，需要先检查模板结构")
        p = paragraphs[idx]
        run = p.add_run(text)
        style_run(run)
        style_para(p, indent=idx == 0 and len(lines) == 1 and not text.startswith("（"))
        used += max(1, -(-len(text) // CHARS_PER_LINE))
    return used


def estimate(lines, first_indent=False) -> int:
    total = 0
    for i, text in enumerate(lines):
        limit = CHARS_PER_LINE - (2 if (first_indent and i == 0) else 0)
        total += max(1, -(-len(text) // limit))
    return total


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"模板不存在：{SRC}")

    # 行数预检：任何一节超出固定行高都会被裁切，必须先算后写
    budget = {1: 5, 2: 6, 3: 9, 4: 20}          # 各节可用正文行数（按行高保守折算）
    need = {
        1: estimate([SEC1], first_indent=True),
        2: estimate(SEC2),
        3: estimate(SEC3),
        4: estimate(SEC4),
    }
    for k in budget:
        flag = "OK" if need[k] <= budget[k] else "超出"
        print(f"第{k}节 需要 {need[k]} 行 / 预算 {budget[k]} 行 → {flag}")
        if need[k] > budget[k]:
            raise SystemExit(f"第{k}节内容过长，会超出固定行高导致显示不全，请精简后再运行")

    shutil.copyfile(SRC, DST)
    doc = Document(DST)
    table = doc.tables[0]

    # 表头：班级（其余留给学生手填）
    row0 = unique_cells(table.rows[0])
    set_cell_text(row0[3], "计科23-1班")

    # 题目名称
    row2 = unique_cells(table.rows[2])
    set_cell_text(row2[1], TITLE)

    # 题目来源：在"教学（含实验）辅助"后打勾
    row3 = unique_cells(table.rows[3])
    para = row3[1].paragraphs[0]
    for run in para.runs:
        if "教学（含实验）辅助" in run.text:
            run.text = run.text.replace("教学（含实验）辅助：", "教学（含实验）辅助：√")
            break
    else:
        raise SystemExit("未在题目来源单元格找到目标文本")

    # 四节正文
    fill_block(unique_cells(table.rows[6])[0], [SEC1])
    fill_block(unique_cells(table.rows[7])[0], SEC2)
    fill_block(unique_cells(table.rows[8])[0], SEC3)
    fill_block(unique_cells(table.rows[9])[0], SEC4)

    doc.save(DST)
    print(f"已生成：{DST.name}")


if __name__ == "__main__":
    main()
