# -*- coding: utf-8 -*-
"""规则设置窗口：查看/启用/停用/新建/编辑用户自定义规则。

规则保存在 rules/custom_rules.json，界面改完立刻生效，不需要改代码。
"""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import messagebox, ttk

from .customrules import PROPS, SCOPES, TARGETS, CustomRule, RuleConfig
from .model import Severity

TYPE_LABELS = {
    "text": "文本检查（正则）",
    "format": "格式检查（字体/字号/行距）",
    "length": "字数检查（某小节）",
    "count": "数量检查（文献/关键词）",
}
TYPE_BY_LABEL = {v: k for k, v in TYPE_LABELS.items()}
SCOPE_BY_LABEL = {v: k for k, v in SCOPES.items()}
SEV_LABELS = ["错误", "警告", "提示"]
MODE_LABELS = {"forbid": "禁止出现", "require": "必须出现"}
MODE_BY_LABEL = {v: k for k, v in MODE_LABELS.items()}
PROP_BY_LABEL = {v: k for k, v in PROPS.items()}
TARGET_BY_LABEL = {v: k for k, v in TARGETS.items()}


class RuleDialog(tk.Toplevel):
    def __init__(self, master, config: RuleConfig, on_change=None):
        super().__init__(master)
        self.title("规则设置 · 自定义检查规则")
        self.geometry("820x460")
        self.transient(master)
        self.config_data = config
        self.on_change = on_change

        ttk.Label(self, text=f"配置文件：{config.path}",
                  foreground="#666", padding=(10, 8)).pack(fill="x")

        body = ttk.Frame(self, padding=(10, 0))
        body.pack(fill="both", expand=True)

        columns = ("enabled", "id", "name", "type", "scope", "severity")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", height=12)
        for key, title, width in (("enabled", "启用", 50), ("id", "编号", 60),
                                  ("name", "名称", 240), ("type", "类型", 90),
                                  ("scope", "范围", 80), ("severity", "级别", 60)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _e: self.edit_rule())

        side = ttk.Frame(body, padding=(10, 0))
        side.pack(side="left", fill="y")
        ttk.Button(side, text="新建规则", command=self.new_rule).pack(fill="x", pady=2)
        ttk.Button(side, text="编辑", command=self.edit_rule).pack(fill="x", pady=2)
        ttk.Button(side, text="启用 / 停用", command=self.toggle).pack(fill="x", pady=2)
        ttk.Button(side, text="删除", command=self.delete_rule).pack(fill="x", pady=2)
        ttk.Separator(side).pack(fill="x", pady=8)
        ttk.Button(side, text="保存并关闭", command=self.save_close).pack(fill="x", pady=2)

        self.status = tk.StringVar(value="双击某行可以编辑；内置的 R 开头规则不在本窗口管理")
        ttk.Label(self, textvariable=self.status, foreground="#666",
                  padding=(10, 6)).pack(fill="x")
        self.refresh()

    # ---------- 列表 ----------

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for rule in self.config_data.rules:
            self.tree.insert("", "end", iid=rule.id, values=(
                "✓" if rule.enabled else "",
                rule.id,
                rule.name,
                TYPE_LABELS.get(rule.type, rule.type),
                SCOPES.get(rule.scope, rule.scope),
                rule.severity.value,
            ))

    def _selected(self) -> CustomRule | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return next((r for r in self.config_data.rules if r.id == selection[0]), None)

    # ---------- 动作 ----------

    def new_rule(self) -> None:
        RuleForm(self, self.config_data, None, on_saved=self._saved)

    def edit_rule(self) -> None:
        rule = self._selected()
        if rule is None:
            messagebox.showinfo("提示", "请先选中一条规则", parent=self)
            return
        RuleForm(self, self.config_data, rule, on_saved=self._saved)

    def toggle(self) -> None:
        rule = self._selected()
        if rule is None:
            return
        rule.enabled = not rule.enabled
        self.config_data.save()
        self.refresh()
        self.status.set(f"{rule.id} 已{'启用' if rule.enabled else '停用'}")

    def delete_rule(self) -> None:
        rule = self._selected()
        if rule is None:
            return
        if not messagebox.askokcancel("删除规则", f"删除规则「{rule.name}」？", parent=self):
            return
        self.config_data.rules = [r for r in self.config_data.rules if r.id != rule.id]
        self.config_data.save()
        self.refresh()
        self.status.set(f"已删除 {rule.id}")

    def _saved(self) -> None:
        self.config_data.save()
        self.refresh()
        if self.on_change:
            self.on_change()

    def save_close(self) -> None:
        self.config_data.save()
        if self.on_change:
            self.on_change()
        self.destroy()


class RuleForm(tk.Toplevel):
    def __init__(self, master: RuleDialog, config: RuleConfig,
                 rule: CustomRule | None, on_saved=None):
        super().__init__(master)
        self.title("编辑规则" if rule else "新建规则")
        self.geometry("560x480")
        self.transient(master)
        self.config_data = config
        self.rule = rule
        self.on_saved = on_saved
        self.dynamic = None
        self.vars: dict[str, tk.StringVar] = {}

        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        self._row(frame, 0, "名称", "name", ttk.Entry(frame, textvariable=self._var("name")))
        type_box = ttk.Combobox(frame, state="readonly",
                                values=list(TYPE_LABELS.values()),
                                textvariable=self._var("type_label"))
        self._row(frame, 1, "类型", "type_label", type_box)
        type_box.bind("<<ComboboxSelected>>", lambda _e: self._build_dynamic())

        scope_box = ttk.Combobox(frame, state="readonly", values=list(SCOPES.values()),
                                 textvariable=self._var("scope_label"))
        self._row(frame, 2, "范围", "scope_label", scope_box)
        scope_box.bind("<<ComboboxSelected>>", lambda _e: self._build_dynamic())

        self._row(frame, 3, "级别", "severity",
                  ttk.Combobox(frame, state="readonly", values=SEV_LABELS,
                               textvariable=self._var("severity")))
        self._row(frame, 4, "提示语", "message", ttk.Entry(frame, textvariable=self._var("message")))

        self.dynamic_frame = ttk.LabelFrame(frame, text="检查条件", padding=10)
        self.dynamic_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 6))

        buttons = ttk.Frame(self, padding=(14, 0, 14, 14))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="保存", command=self.save).pack(side="right", padx=8)

        self._fill(rule)
        self._build_dynamic()

    def _var(self, name: str) -> tk.StringVar:
        if name not in self.vars:
            self.vars[name] = tk.StringVar()
        return self.vars[name]

    @staticmethod
    def _row(frame, row: int, label: str, key: str, widget):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))
        widget.grid(row=row, column=1, sticky="ew", pady=4)
        return widget

    def _fill(self, rule: CustomRule | None) -> None:
        if rule is None:
            self._var("type_label").set(TYPE_LABELS["text"])
            self._var("scope_label").set(SCOPES["body"])
            self._var("severity").set("警告")
            self._var("mode").set(MODE_LABELS["forbid"])
            self._var("prop").set(PROPS["font"])
            self._var("target").set(TARGETS["references"])
            return
        self._var("name").set(rule.name)
        self._var("type_label").set(TYPE_LABELS.get(rule.type, TYPE_LABELS["text"]))
        self._var("scope_label").set(SCOPES.get(rule.scope, SCOPES["body"]))
        self._var("severity").set(rule.severity.value)
        self._var("message").set(rule.message)
        self._var("mode").set(MODE_LABELS.get(rule.mode, MODE_LABELS["forbid"]))
        self._var("prop").set(PROPS.get(rule.prop, PROPS["font"]))
        self._var("target").set(TARGETS.get(rule.target, TARGETS["references"]))
        self._var("section").set(rule.section)
        self._var("pattern").set(rule.pattern)
        self._var("expect").set("" if rule.expect is None else str(rule.expect))
        self._var("min").set("" if rule.min is None else str(rule.min))
        self._var("max").set("" if rule.max is None else str(rule.max))

    def _build_dynamic(self) -> None:
        for child in self.dynamic_frame.winfo_children():
            child.destroy()
        kind = TYPE_BY_LABEL.get(self._var("type_label").get(), "text")
        scope = SCOPE_BY_LABEL.get(self._var("scope_label").get(), "body")
        frame = self.dynamic_frame
        frame.columnconfigure(1, weight=1)

        def row(index, label, key):
            ttk.Label(frame, text=label).grid(row=index, column=0, sticky="w", pady=3, padx=(0, 8))
            entry = ttk.Entry(frame, textvariable=self._var(key))
            entry.grid(row=index, column=1, sticky="ew", pady=3)
            return entry

        if kind == "text":
            ttk.Label(frame, text="方式").grid(row=0, column=0, sticky="w", pady=3)
            ttk.Combobox(frame, state="readonly", values=list(MODE_LABELS.values()),
                         textvariable=self._var("mode")).grid(row=0, column=1, sticky="ew", pady=3)
            row(1, "正则表达式", "pattern")
            if scope == "section":
                row(2, "小节名称", "section")
            ttk.Label(frame, text="例：笔者认为|综上所述 ；支持 \\d、\\[(J|M)\\] 等写法",
                      foreground="#888").grid(row=3, column=0, columnspan=2, sticky="w")
        elif kind == "format":
            ttk.Label(frame, text="属性").grid(row=0, column=0, sticky="w", pady=3)
            ttk.Combobox(frame, state="readonly", values=list(PROPS.values()),
                         textvariable=self._var("prop")).grid(row=0, column=1, sticky="ew", pady=3)
            row(1, "期望值", "expect")
            ttk.Label(frame, text="字体填名称（如 宋体）；字号、行距填数字（如 12、20）",
                      foreground="#888").grid(row=2, column=0, columnspan=2, sticky="w")
        elif kind == "length":
            row(0, "小节名称", "section")
            row(1, "最少字数", "min")
            row(2, "最多字数", "max")
        else:
            ttk.Label(frame, text="统计对象").grid(row=0, column=0, sticky="w", pady=3)
            ttk.Combobox(frame, state="readonly", values=list(TARGETS.values()),
                         textvariable=self._var("target")).grid(row=0, column=1, sticky="ew", pady=3)
            row(1, "最少", "min")
            row(2, "最多", "max")

    def save(self) -> None:
        name = self._var("name").get().strip()
        if not name:
            messagebox.showwarning("缺少名称", "请填写规则名称", parent=self)
            return
        kind = TYPE_BY_LABEL.get(self._var("type_label").get(), "text")
        scope = SCOPE_BY_LABEL.get(self._var("scope_label").get(), "body")
        severity = {"错误": Severity.ERROR, "警告": Severity.WARN,
                    "提示": Severity.INFO}[self._var("severity").get()]

        rule = self.rule or CustomRule(id=self._next_id(), name=name)
        rule.name = name
        rule.type = kind
        rule.scope = scope
        rule.severity = severity
        rule.message = self._var("message").get().strip()
        rule.enabled = True

        if kind == "text":
            pattern = self._var("pattern").get()
            try:
                re.compile(pattern)
            except re.error as exc:
                messagebox.showwarning("正则无效", f"正则表达式有误：{exc}", parent=self)
                return
            rule.pattern = pattern
            rule.mode = MODE_BY_LABEL.get(self._var("mode").get(), "forbid")
            rule.section = self._var("section").get().strip()
            if scope == "section" and not rule.section:
                messagebox.showwarning("缺少小节", "范围选了“指定小节”，请填写小节名称", parent=self)
                return
        elif kind == "format":
            rule.prop = PROP_BY_LABEL.get(self._var("prop").get(), "font")
            raw = self._var("expect").get().strip()
            rule.expect = raw if rule.prop == "font" else _to_number(raw)
            if rule.expect in ("", None):
                messagebox.showwarning("缺少期望值", "请填写期望值", parent=self)
                return
        elif kind == "length":
            rule.section = self._var("section").get().strip()
            if not rule.section:
                messagebox.showwarning("缺少小节", "请填写小节名称，如“摘要”", parent=self)
                return
            rule.min = _to_number(self._var("min").get())
            rule.max = _to_number(self._var("max").get())
        else:
            rule.target = TARGET_BY_LABEL.get(self._var("target").get(), "references")
            rule.min = _to_number(self._var("min").get())
            rule.max = _to_number(self._var("max").get())

        if self.rule is None:
            self.config_data.rules.append(rule)
        self.config_data.save()
        if self.on_saved:
            self.on_saved()
        self.destroy()

    def _next_id(self) -> str:
        numbers = []
        for rule in self.config_data.rules:
            match = re.fullmatch(r"C(\d+)", rule.id)
            if match:
                numbers.append(int(match.group(1)))
        return f"C{(max(numbers) + 1) if numbers else 1:03d}"


def _to_number(text: str):
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return int(value) if value.is_integer() else value
