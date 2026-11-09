# -*- coding: utf-8 -*-
"""生成一份“故意违规”的样本 docx，用来验证规则引擎的检出效果。

样本里每条违规都对应一个规则编号，方便统计检出率：
    R001 字体     R002 字号     R003 行距     R004 层级跳级
    R006 摘要字数 R007 关键词数 R008 无目录域 R009 图号不连续
    R010 题注格式 R011 结论字数 R012 文献不足 R013 缺英文文献
    R014 英文数字字体 R015 连续空段落 R016 标题缺空格 R017 摘要含引用
    R018 中文数字章号
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Pt

OUT = Path(__file__).with_name("bad_report.docx")


def set_font(run, name: str, size: float) -> None:
    run.font.name = name
    run.font.size = Pt(size)
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), name)


def para(doc, text: str, *, font="宋体", size=12.0, spacing=20.0, exact=True,
         style=None, bold=False):
    p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    run = p.add_run(text)
    set_font(run, font, size)
    run.bold = bold
    fmt = p.paragraph_format
    if exact:
        fmt.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        fmt.line_spacing = Pt(spacing)
    else:
        fmt.line_spacing = spacing
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(0)
    return p


def para_mixed(doc, parts, *, size=12.0, spacing=20.0):
    """多 run 段落：用来验证“英文/数字字体”这类按 run 判定的规则。"""
    p = doc.add_paragraph()
    for text, font in parts:
        set_font(p.add_run(text), font, size)
    fmt = p.paragraph_format
    fmt.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    fmt.line_spacing = Pt(spacing)
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(0)
    return p


def heading(doc, text: str, level: int, *, page_break=False):
    p = doc.add_paragraph(style=f"Heading {level}")
    run = p.add_run(text)
    set_font(run, "黑体", {1: 18.0, 2: 15.0, 3: 14.0}[level])
    p.paragraph_format.page_break_before = page_break
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    p.paragraph_format.line_spacing = Pt(20)
    return p


def build() -> Path:
    doc = Document()

    para(doc, "基于 Web 的图书管理系统设计与实现", font="黑体", size=18, bold=True)

    # 摘要：字数不足（约 90 字）+ 含引用（R017）
    heading(doc, "摘　要", 1)
    para(doc, "本文设计了一个图书管理系统，采用 Java 语言开发，数据库使用 MySQL，"
              "实现了图书的增删改查功能，系统界面友好，操作简单，具有一定的实用价值[1]。",
         size=12)
    para(doc, "关键词：图书管理，Java", size=12)

    # 没有目录域（R008）
    heading(doc, "目　录", 1)
    para(doc, "第1章 概述 ……………………………………… 1", size=12)

    heading(doc, "第1章 概述", 1, page_break=True)
    # 层级跳级：H1 后直接 H3（R004）
    heading(doc, "1.1.1 研究背景", 3)
    # 正常段落：宋体小四、固定 20 磅（不报错）
    para(doc, "随着计算机技术的发展，图书馆的管理方式由人工管理逐步转向信息化管理，"
              "图书管理系统的应用能够显著提高图书借阅与归还的效率，减少人工登记的错误。")

    # 英文/数字字体错误（R014）：ASCII 片段用了宋体而非 Times New Roman
    para_mixed(doc, [("系统部署于 ", "宋体"), ("Windows11 Professional", "宋体"), (" 环境下运行。", "宋体")])

    # 字体错误（R001）：等线
    para(doc, "本系统的开发环境为 Windows11 操作系统，开发工具采用 IntelliJ IDEA，"
              "运行环境为 JDK8，使用 Tomcat 作为 Web 服务器。", font="等线")
    # 字号错误（R002）：11 磅
    para(doc, "系统采用 B/S 三层架构，表现层使用 JSP 页面，业务逻辑层使用 Servlet 实现，"
              "数据访问层通过 JDBC 连接 MySQL 数据库完成数据持久化操作。", size=11.0)
    # 行距错误（R003）：1.5 倍
    para(doc, "在数据库设计阶段，系统共设计了图书信息表、读者信息表、借阅记录表三张核心"
              "数据表，并通过外键约束保证借阅记录与图书、读者之间的数据一致性。", spacing=1.5, exact=False)

    # 口语化表述（自定义规则 C001）
    para(doc, "笔者认为该系统具有较高的实用价值，界面友好且操作便捷，适合在高校图书馆推广使用。")

    # 标题序号缺空格（R016）
    heading(doc, "1.3设计内容", 2)
    para(doc, "本章主要介绍系统的设计内容，包括功能模块划分、数据库设计以及界面设计三个部分，"
              "各部分的具体实现将在后续章节中详细说明。")

    # 图号不连续（R009）：1-1 之后是 1-3
    para(doc, "系统总体结构如图1-1所示。", size=12)
    para(doc, "图1-1 系统总体结构图", font="宋体", size=12)          # 题注字体错误（R010）
    para(doc, "用户登录流程如图1-3所示。", size=12)
    para(doc, "图1-3 用户登录流程图", font="宋体", size=12)

    # 连续空段落（R015）
    for _ in range(4):
        doc.add_paragraph("")

    # 中文数字章号（R018）
    heading(doc, "第二章 需求分析", 1, page_break=True)
    para(doc, "本章从功能需求与性能需求两个方面对系统进行分析，明确系统需要实现的功能，"
              "以及系统在响应时间、并发用户数等方面的性能指标要求。")

    heading(doc, "第3章 系统设计", 1, page_break=True)
    para(doc, "系统采用 MVC 设计模式，将视图、控制器与模型分离，降低了模块之间的耦合度，"
              "便于后期维护与功能扩展，符合软件工程的设计原则。")

    # 结论字数不足（R011）
    heading(doc, "结　论", 1)
    para(doc, "本文完成了图书管理系统的设计与实现，实现了图书管理的基本功能，达到了预期目标。")

    # 参考文献不足（R012）且没有英文文献（R013）
    heading(doc, "参考文献", 1)
    para(doc, "[1] 张三. Java Web 开发实战[M]. 北京：人民邮电出版社，2020：12-18.")
    para(doc, "[2] 李四. 基于 Java 的图书管理系统设计[J]. 计算机应用，2021，(03)：45-48.")
    para(doc, "[3] 王五. 数据库原理与应用[M]. 北京：清华大学出版社，2019：66-72.")
    para(doc, "[4] 赵六. 软件工程导论[M]. 北京：机械工业出版社，2018：30-35.")
    para(doc, "[5] 孙七. 基于 B/S 架构的管理系统研究[D]. 成都：电子科技大学，2020：5-9.")

    doc.save(OUT)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"已生成样本：{path}")
