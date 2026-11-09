# -*- coding: utf-8 -*-
"""统计图表：直接用 tkinter Canvas 画，不引入 matplotlib 依赖。

两幅图：
    draw_level_pie  按严重级别（错误/警告/提示）的分布
    draw_rule_bar   命中次数最多的规则 TOP N
"""
from __future__ import annotations

import tkinter as tk

LEVEL_COLORS = {"错误": "#d9534f", "警告": "#f0ad4e", "提示": "#5bc0de"}
RULE_COLORS = ["#4a7ebb", "#6aa4d8", "#8cc0e8", "#a9d3f0", "#c7e3f7",
               "#d9534f", "#e8845f", "#f0ad4e", "#8ec07c", "#b8bb26"]


def clear(canvas: tk.Canvas) -> None:
    canvas.delete("all")


def draw_level_pie(canvas: tk.Canvas, counts: dict[str, int], title: str = "问题级别分布") -> None:
    clear(canvas)
    width = max(canvas.winfo_width(), 260)
    height = max(canvas.winfo_height(), 220)
    total = sum(counts.values())

    canvas.create_text(14, 12, text=title, anchor="nw", fill="#333",
                       font=("PingFang SC", 12, "bold"))

    if total == 0:
        canvas.create_text(width / 2, height / 2, text="没有发现问题", fill="#999")
        return

    size = min(width * 0.42, height * 0.62)
    x0 = 24
    y0 = 44
    start = 90.0
    for level in ("错误", "警告", "提示"):
        value = counts.get(level, 0)
        if value <= 0:
            continue
        extent = -360.0 * value / total
        canvas.create_arc(x0, y0, x0 + size, y0 + size, start=start, extent=extent,
                          fill=LEVEL_COLORS[level], outline="white", width=2)
        start += extent

    legend_x = x0 + size + 26
    legend_y = y0 + 6
    for index, level in enumerate(("错误", "警告", "提示")):
        value = counts.get(level, 0)
        percent = value / total * 100 if total else 0
        canvas.create_rectangle(legend_x, legend_y, legend_x + 12, legend_y + 12,
                                fill=LEVEL_COLORS[level], outline="")
        canvas.create_text(legend_x + 20, legend_y + 6,
                           text=f"{level}  {value} 条（{percent:.0f}%）",
                           anchor="w", fill="#333", font=("PingFang SC", 11))
        legend_y += 26

    canvas.create_text(x0, y0 + size + 18, text=f"合计 {total} 条", anchor="w", fill="#666")


def draw_rule_bar(canvas: tk.Canvas, items: list[tuple[str, int]], title: str = "命中最多的规则") -> None:
    clear(canvas)
    width = max(canvas.winfo_width(), 320)
    height = max(canvas.winfo_height(), 220)
    canvas.create_text(14, 12, text=title, anchor="nw", fill="#333",
                       font=("PingFang SC", 12, "bold"))

    items = [(label, count) for label, count in items if count > 0][:8]
    if not items:
        canvas.create_text(width / 2, height / 2, text="没有发现问题", fill="#999")
        return

    top = max(count for _, count in items)
    left = 14
    label_width = 156
    bar_area = max(width - left - label_width - 46, 60)
    y = 46
    row_height = min(28, max(18, (height - 60) / len(items)))
    for index, (label, count) in enumerate(items):
        text = label if len(label) <= 15 else label[:15] + "…"
        canvas.create_text(left, y + row_height / 2, text=text, anchor="w",
                           fill="#333", font=("PingFang SC", 9))
        bar_len = bar_area * count / top
        canvas.create_rectangle(left + label_width, y + 4,
                                left + label_width + bar_len, y + row_height - 4,
                                fill=RULE_COLORS[index % len(RULE_COLORS)], outline="")
        canvas.create_text(left + label_width + bar_len + 6, y + row_height / 2,
                           text=str(count), anchor="w", fill="#555",
                           font=("PingFang SC", 10))
        y += row_height
