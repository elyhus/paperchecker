# -*- coding: utf-8 -*-
"""桌面界面（Tkinter）

三个页签：
    问题清单  逐条问题 + 实际值/期望值
    统计图表  级别饼图 + 规则命中柱状图（Canvas 绘制，无第三方依赖）
    批量检查  多文件/文件夹批量检查、批量修复、汇总导出
"""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import batch, charts, customrules, engine, fixer, llm, report, store
from .model import Policy
from .ruledialog import RuleDialog

APP_TITLE = "PaperChecker · 论文格式合规检查（v1.0）"


class App(tk.Tk):
    def __init__(self, demo_top: bool = False) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x740")
        self.minsize(980, 620)

        self.file_path: Path | None = None
        self.result: engine.CheckResult | None = None
        self.batch_result: batch.BatchResult | None = None
        self.batch_files: list[Path] = []
        self.task_id: int | None = None
        self.config = customrules.load()
        self.semantic_issues: list = []

        self._build_toolbar()
        self._build_tabs()
        self._build_status()

        self.update_idletasks()
        self.geometry("1180x740+90+60")
        self.lift()
        self.focus_force()
        if demo_top:
            self.attributes("-topmost", True)

    # ---------------- 界面骨架 ----------------

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(10, 8))
        bar.pack(fill="x")

        ttk.Button(bar, text="选择文档…", command=self.choose_file).pack(side="left")
        self.path_var = tk.StringVar(value="未选择文件（支持 .docx）")
        ttk.Label(bar, textvariable=self.path_var, foreground="#555").pack(side="left", padx=10)

        ttk.Button(bar, text="模型设置", command=self.setup_model).pack(side="right", padx=4)
        ttk.Button(bar, text="规则设置", command=self.open_rules).pack(side="right", padx=4)
        ttk.Button(bar, text="导出报告", command=self.export_report).pack(side="right", padx=4)
        self.fix_btn = ttk.Button(bar, text="一键修复", command=self.run_fix, state="disabled")
        self.fix_btn.pack(side="right", padx=4)
        self.semantic_btn = ttk.Button(bar, text="语义检查", command=self.run_semantic, state="disabled")
        self.semantic_btn.pack(side="right", padx=4)
        self.check_btn = ttk.Button(bar, text="开始检查", command=self.run_check, state="disabled")
        self.check_btn.pack(side="right", padx=4)

    def _build_tabs(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 4))
        self._build_issue_tab()
        self._build_chart_tab()
        self._build_batch_tab()

    def _build_issue_tab(self) -> None:
        page = ttk.Frame(self.notebook)
        self.notebook.add(page, text="问题清单")
        columns = ("severity", "rule", "location", "message")
        self.tree = ttk.Treeview(page, columns=columns, show="headings")
        for key, title, width in (("severity", "级别", 58), ("rule", "规则", 62),
                                  ("location", "位置", 300), ("message", "说明", 560)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="w")
        scroll = ttk.Scrollbar(page, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.show_detail)

    def _build_chart_tab(self) -> None:
        page = ttk.Frame(self.notebook)
        self.notebook.add(page, text="统计图表")
        page.columnconfigure(0, weight=1)
        page.columnconfigure(1, weight=1)
        page.rowconfigure(0, weight=1)

        self.pie_canvas = tk.Canvas(page, background="white", highlightthickness=1,
                                    highlightbackground="#ddd")
        self.pie_canvas.grid(row=0, column=0, sticky="nsew", padx=(4, 6), pady=4)
        self.bar_canvas = tk.Canvas(page, background="white", highlightthickness=1,
                                    highlightbackground="#ddd")
        self.bar_canvas.grid(row=0, column=1, sticky="nsew", padx=(6, 4), pady=4)

        self.stats_tree = ttk.Treeview(page, columns=("rule", "name", "count"), show="headings", height=7)
        for key, title, width in (("rule", "规则", 90), ("name", "名称", 420), ("count", "数量", 90)):
            self.stats_tree.heading(key, text=title)
            self.stats_tree.column(key, width=width, anchor="w")
        self.stats_tree.grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=(0, 4))

        self.pie_canvas.bind("<Configure>", lambda _e: self._draw_charts())
        self.bar_canvas.bind("<Configure>", lambda _e: self._draw_charts())

    def _build_batch_tab(self) -> None:
        page = ttk.Frame(self.notebook)
        self.notebook.add(page, text="批量检查")

        bar = ttk.Frame(page, padding=(4, 6))
        bar.pack(fill="x")
        ttk.Button(bar, text="添加文件…", command=self.batch_add_files).pack(side="left")
        ttk.Button(bar, text="添加文件夹…", command=self.batch_add_folder).pack(side="left", padx=6)
        ttk.Button(bar, text="清空", command=self.batch_clear).pack(side="left")
        ttk.Button(bar, text="导出汇总", command=self.batch_export).pack(side="right", padx=4)
        ttk.Button(bar, text="批量修复", command=self.batch_fix).pack(side="right", padx=4)
        ttk.Button(bar, text="开始批量检查", command=self.batch_run).pack(side="right", padx=4)

        columns = ("file", "error", "warn", "info", "fixable", "time")
        self.batch_tree = ttk.Treeview(page, columns=columns, show="headings", height=12)
        for key, title, width in (("file", "文件", 420), ("error", "错误", 60),
                                  ("warn", "警告", 60), ("info", "提示", 60),
                                  ("fixable", "可修复", 70), ("time", "耗时", 80)):
            self.batch_tree.heading(key, text=title)
            self.batch_tree.column(key, width=width, anchor="w")
        self.batch_tree.pack(fill="both", expand=True, padx=4)

        self.batch_text = tk.Text(page, height=6, wrap="word", background="#f7f7f7", relief="flat")
        self.batch_text.pack(fill="x", padx=4, pady=4)

    def _build_status(self) -> None:
        self.detail_var = tk.StringVar(value="选中一条问题可查看「实际 / 应为」")
        ttk.Label(self, textvariable=self.detail_var, padding=(12, 2),
                  foreground="#333").pack(fill="x")
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w",
                  padding=(8, 4)).pack(fill="x", side="bottom")

    # ---------------- 单文档 ----------------

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择要检查的文档", filetypes=[("Word 文档", "*.docx"), ("所有文件", "*.*")])
        if not path:
            return
        self.file_path = Path(path)
        self.path_var.set(str(self.file_path))
        self.check_btn.config(state="normal")
        self.fix_btn.config(state="disabled")
        self.semantic_btn.config(state="disabled")
        self.status_var.set("已选择文件，点击“开始检查”")

    def run_check(self) -> None:
        if not self.file_path:
            return
        self.status_var.set("检查中…")
        self.update_idletasks()
        try:
            self.result = engine.run(self.file_path, config=self.config)
        except Exception as exc:
            messagebox.showerror("检查失败", f"无法解析该文档：\n{exc}")
            self.status_var.set("检查失败")
            return
        self.semantic_issues = []
        self.render(self.result)
        counts = self.result.counts
        self.status_var.set(
            f"完成，用时 {self.result.duration * 1000:.0f} ms · 错误 {counts['错误']}"
            f" · 警告 {counts['警告']} · 提示 {counts['提示']} · 可修复 {len(self.result.fixable)} 项")
        self.fix_btn.config(state="normal" if self.result.fixable else "disabled")
        self.semantic_btn.config(state="normal" if llm.load_key() else "disabled")
        try:
            self.task_id = store.save_result(self.result)
            store.sync_rules(self.config)
        except Exception:
            pass

    def render(self, result: engine.CheckResult) -> None:
        self.tree.delete(*self.tree.get_children())
        for issue in result.issues:
            self.tree.insert("", "end", values=(
                issue.severity.value, issue.rule_id, issue.location, issue.message))
        self.stats_tree.delete(*self.stats_tree.get_children())
        for stat in result.stats:
            self.stats_tree.insert("", "end", values=(stat.rule_id, stat.rule_name, stat.total))
        self._draw_charts()

    def _draw_charts(self) -> None:
        if not self.result:
            return
        charts.draw_level_pie(self.pie_canvas, self.result.counts)
        items = [(f"{s.rule_id} {s.rule_name}", s.total) for s in
                 sorted(self.result.stats, key=lambda s: -s.total)[:8]]
        charts.draw_rule_bar(self.bar_canvas, items)

    def show_detail(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection or not self.result:
            return
        issue = self.result.issues[self.tree.index(selection[0])]
        self.detail_var.set(
            f"[{issue.rule_id}] {issue.message}   实际：{issue.actual or '-'}"
            f"   应为：{issue.expected or '-'}   {'可自动修复' if issue.fixable else '需手工修改'}")

    def run_semantic(self) -> None:
        if not self.result:
            return
        key = llm.load_key()
        if not key:
            messagebox.showinfo("需要 API Key", "语义检查需要大模型，请先点“模型设置”填写 Key。")
            return
        self.semantic_btn.config(state="disabled")
        self.status_var.set("语义检查中（调用大模型）…")

        def worker():
            cfg = llm.LLMConfig(api_key=key)
            try:
                issues, raw = llm.semantic_issues(self.result.doc, cfg)
            except Exception as exc:
                issues, raw = [], {"error": str(exc)}
            self.after(0, lambda: self._semantic_done(issues, raw))

        threading.Thread(target=worker, daemon=True).start()

    def _semantic_done(self, issues, raw) -> None:
        self.semantic_btn.config(state="normal")
        self.semantic_issues = issues
        if issues:
            self.result.issues.extend(issues)
            self.render(self.result)
        if raw.get("error"):
            messagebox.showwarning("语义检查失败", f"模型调用失败，已跳过：\n{raw['error'][:200]}")
            self.status_var.set("语义检查失败（不影响格式检查结果）")
        elif raw.get("skipped"):
            messagebox.showinfo("已跳过", raw["skipped"])
            self.status_var.set("语义检查已跳过")
        else:
            self.status_var.set(f"语义检查完成，新增 {len(issues)} 条建议")
        try:
            if self.task_id:
                store.save_semantic(self.task_id, raw)
                store.save_model_config("openai-compatible", "https://api.deepseek.com/v1", "deepseek-chat")
        except Exception:
            pass

    def run_fix(self) -> None:
        if not self.result or not self.file_path:
            return
        targets = self.result.fixable
        if not targets:
            messagebox.showinfo("无需修复", "没有可自动修复的问题")
            return
        changes = fixer.preview(self.result.doc, targets)
        head = "\n".join(c.as_row() for c in changes[:12])
        more = f"\n… 其余 {len(changes) - 12} 处" if len(changes) > 12 else ""
        if not messagebox.askokcancel(
                "确认修复", f"将修改 {len(changes)} 处：\n\n{head}{more}\n\n原文件会先自动备份，是否继续？"):
            return
        policy = self.config.policy()
        backup_path, applied = fixer.apply(
            self.file_path, targets,
            policy_body_font=policy.body_font,
            policy_body_size=policy.body_size_pt,
            policy_line=policy.body_line_pt)
        try:
            if self.task_id:
                store.save_fixes(self.task_id, applied, str(backup_path))
        except Exception:
            pass
        messagebox.showinfo("完成", f"已备份为：{backup_path.name}\n修复 {len(applied)} 处，将重新检查")
        self.run_check()

    def export_report(self) -> None:
        if not self.result:
            messagebox.showinfo("提示", "请先检查文档")
            return
        path = filedialog.asksaveasfilename(
            title="导出检查报告", defaultextension=".md",
            initialfile=f"{self.file_path.stem}-检查报告.md",
            filetypes=[("Markdown", "*.md"), ("JSON", "*.json")])
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() == ".json":
            report.dump_json(self.result, target)
        else:
            target.write_text(report.markdown(self.result), encoding="utf-8")
        messagebox.showinfo("已导出", str(target))

    # ---------------- 规则 ----------------

    def open_rules(self) -> None:
        RuleDialog(self, self.config, on_change=self.on_rules_changed)

    def on_rules_changed(self) -> None:
        if self.result and self.file_path:
            self.run_check()
            self.status_var.set(self.status_var.get() + " · 已按新规则重新检查")

    # ---------------- 批量 ----------------

    def batch_add_files(self) -> None:
        paths = filedialog.askopenfilenames(title="选择要检查的文档",
                                            filetypes=[("Word 文档", "*.docx")])
        for item in paths:
            path = Path(item)
            if path not in self.batch_files:
                self.batch_files.append(path)
        self._refresh_batch_list()

    def batch_add_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择文件夹（检查其中的 docx）")
        if not folder:
            return
        for path in batch.collect([folder]):
            if path not in self.batch_files:
                self.batch_files.append(path)
        self._refresh_batch_list()

    def batch_clear(self) -> None:
        self.batch_files = []
        self.batch_result = None
        self._refresh_batch_list()
        self.batch_tree.delete(*self.batch_tree.get_children())
        self.batch_text.delete("1.0", "end")

    def _refresh_batch_list(self) -> None:
        self.batch_tree.delete(*self.batch_tree.get_children())
        for path in self.batch_files:
            self.batch_tree.insert("", "end", values=(str(path), "", "", "", "", ""))
        self.status_var.set(f"批量列表：{len(self.batch_files)} 个文件")

    def batch_run(self) -> None:
        if not self.batch_files:
            messagebox.showinfo("提示", "先添加要检查的文件或文件夹")
            return
        self.status_var.set(f"批量检查 {len(self.batch_files)} 个文件…")
        self.update_idletasks()
        self.batch_result = batch.run_batch(self.batch_files, self.config)
        self.batch_tree.delete(*self.batch_tree.get_children())
        for result in self.batch_result.results:
            c = result.counts
            self.batch_tree.insert("", "end", values=(
                str(result.path), c["错误"], c["警告"], c["提示"],
                len(result.fixable), f"{result.duration * 1000:.0f} ms"))
        for path, reason in self.batch_result.failed:
            self.batch_tree.insert("", "end", values=(str(path), "打开失败", reason, "", "", ""))
        counts = self.batch_result.counts
        summary = (f"共 {len(self.batch_result.results)} 个文件，"
                   f"错误 {counts['错误']} · 警告 {counts['警告']} · 提示 {counts['提示']}；"
                   f"可修复 {self.batch_result.fixable} 处；总耗时 {self.batch_result.duration:.1f}s")
        self.batch_text.delete("1.0", "end")
        self.batch_text.insert("1.0", summary)
        self.status_var.set(summary)
        try:
            store.sync_rules(self.config)
            for result in self.batch_result.results:
                store.save_result(result)
        except Exception:
            pass

    def batch_fix(self) -> None:
        if not self.batch_result:
            messagebox.showinfo("提示", "先执行批量检查")
            return
        if not messagebox.askokcancel("批量修复", "将修复所有可修复项，每个文件都会先备份。继续？"):
            return
        report_lines = batch.fix_batch(self.batch_result, self.config)
        self.batch_text.delete("1.0", "end")
        if not report_lines:
            self.batch_text.insert("1.0", "没有可自动修复的项。")
            return
        for path, backup, count in report_lines:
            self.batch_text.insert("end", f"{path.name}：修复 {count} 处，备份 {backup.name}\n")
        self.status_var.set(f"批量修复完成，共处理 {len(report_lines)} 个文件")
        self.batch_run()

    def batch_export(self) -> None:
        if not self.batch_result:
            messagebox.showinfo("提示", "先执行批量检查")
            return
        path = filedialog.asksaveasfilename(
            title="导出汇总报告", defaultextension=".md", initialfile="批量检查汇总.md",
            filetypes=[("Markdown", "*.md")])
        if not path:
            return
        Path(path).write_text(batch.summary_markdown(self.batch_result), encoding="utf-8")
        messagebox.showinfo("已导出", path)

    # ---------------- 模型 ----------------

    def setup_model(self) -> None:
        current = llm.load_key()
        key = simpledialog.askstring(
            "模型 API Key",
            f"语义检查需要大模型（当前后端：{llm.key_backend()}）。\n"
            "Key 保存在系统密钥链，不写入数据库、不上传到任何服务器：",
            show="*", initialvalue=current)
        if key is None:
            return
        if llm.save_key(key):
            messagebox.showinfo("已保存", f"Key 已写入：{llm.key_backend()}")
            if self.result:
                self.semantic_btn.config(state="normal")
        else:
            messagebox.showwarning("未保存", "当前系统不支持密钥链存储，可改用环境变量 PAPERCHECKER_API_KEY")


def main() -> None:
    demo_top = len(sys.argv) > 1 and Path(sys.argv[1]).exists()
    app = App(demo_top=demo_top)
    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1])
        if candidate.exists():
            app.file_path = candidate
            app.path_var.set(str(candidate))
            app.check_btn.config(state="normal")
            app.after(300, app.run_check)
    tab = os.environ.get("PAPERCHECKER_TAB")
    if tab and tab.isdigit():
        app.notebook.select(int(tab))       # 演示/截图时直接打开指定页签
    app.mainloop()


if __name__ == "__main__":
    main()
