# -*- coding: utf-8 -*-
"""PaperChecker · 面向高校论文/文档规范的桌面智能体

模块划分：
    model      数据模型（问题条目、严重级别）
    docmodel   docx 解析，计算段落的“实际生效格式”
    rules      规则库（当前 18 条）
    engine     规则执行与结果聚合
    fixer      一键修复（备份、差异预览、回滚）
    report     控制台 / Markdown / JSON 输出
    store      SQLite 本地存储
    llm        语义检查（需用户自填 API Key，可选）
    cli        命令行入口
    gui        桌面界面入口
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
