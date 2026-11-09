# -*- coding: utf-8 -*-
"""命令行入口：

    python run.py check 文档.docx            # 只检查
    python run.py check 文档.docx --md 报告.md --json 结果.json
    python run.py check 文档.docx --fix      # 预览并确认后修复
    python run.py rules                      # 查看规则库
    python run.py history                    # 查看本机检查历史
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import batch, customrules, engine, fixer, llm, report, store
from .model import Policy, Severity


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paperchecker", description="文档格式合规检查（原型）")
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="检查一个 docx")
    check.add_argument("file", type=Path)
    check.add_argument("--md", type=Path, help="导出 Markdown 报告")
    check.add_argument("--json", type=Path, help="导出 JSON 结果")
    check.add_argument("--db", type=Path, help="写入 SQLite（默认 paperchecker.db）")
    check.add_argument("--fix", action="store_true", help="修复可修复项（会先备份）")
    check.add_argument("--yes", action="store_true", help="跳过修复确认")
    check.add_argument("--min", choices=["错误", "警告", "提示"], help="只显示不低于该级别的问题")
    check.add_argument("--quiet", action="store_true")
    check.add_argument("--rules", type=Path,
                       help="自定义规则文件（默认 rules/custom_rules.json）")
    check.add_argument("--no-custom", action="store_true", help="只跑内置规则")

    check.add_argument("--semantic", action="store_true",
                       help="追加语义检查（需要 API Key，未配置则跳过）")

    batch_cmd = sub.add_parser("batch", help="批量检查文件夹或多个文件")
    batch_cmd.add_argument("paths", nargs="+", type=Path)
    batch_cmd.add_argument("--md", type=Path, help="导出汇总 Markdown")
    batch_cmd.add_argument("--db", type=Path, help="写入 SQLite")
    batch_cmd.add_argument("--rules", type=Path, help="自定义规则文件")

    sub.add_parser("rules", help="列出规则库")
    history = sub.add_parser("history", help="查看检查历史")
    history.add_argument("--db", type=Path, default=Path("paperchecker.db"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "batch":
        config = customrules.load(args.rules)
        result = batch.run_batch(args.paths, config)
        counts = result.counts
        print(f"共 {len(result.results)} 个文件，失败 {len(result.failed)}")
        for item in sorted(result.results, key=lambda r: (-r.counts["错误"], -r.counts["警告"])):
            c = item.counts
            print(f"  {item.path.name:<30} 错{c['错误']:>3} 警{c['警告']:>3} 提{c['提示']:>3} "
                  f"可修复 {len(item.fixable):>2}")
        print(f"合计：错误 {counts['错误']} · 警告 {counts['警告']} · 提示 {counts['提示']} · "
              f"耗时 {result.duration:.1f}s")
        if args.md:
            args.md.write_text(batch.summary_markdown(result), encoding="utf-8")
            print(f"汇总已导出：{args.md}")
        if args.db:
            for item in result.results:
                store.save_result(item, args.db)
            print(f"已写入数据库：{args.db}")
        return 1 if counts["错误"] else 0

    if args.command == "rules":
        from .rules import RULES
        print("内置规则：")
        for item in RULES:
            print(f"  {item.rule_id}  {item.name:<32} [{item.severity.value}]"
                  f"{'  可修复' if item.fixable else ''}")
        config = customrules.load()
        print(f"\n自定义规则（{config.path}）：")
        if not config.rules:
            print("  （空）")
        for rule in config.rules:
            state = "启用" if rule.enabled else "停用"
            print(f"  {rule.id}  {rule.name:<32} [{rule.severity.value}] {rule.type} {state}")
        return 0

    if args.command == "history":
        rows = store.recent_tasks(db_path=args.db)
        if not rows:
            print("还没有检查记录")
            return 0
        for row in rows:
            print(f"#{row['id']:<3} {row['started_at']}  {row['file_name']}  "
                  f"错{row['error_count']}/警{row['warn_count']}/提{row['info_count']}")
        return 0

    if args.command != "check":
        build_parser().print_help()
        return 1

    path = args.file
    if not path.exists():
        print(f"文件不存在：{path}", file=sys.stderr)
        return 2
    if path.suffix.lower() != ".docx":
        print("当前只支持 .docx（.doc 请先另存为 .docx）", file=sys.stderr)
        return 2

    min_severity = {"错误": Severity.ERROR, "警告": Severity.WARN, "提示": Severity.INFO}.get(args.min)
    config = None
    if not args.no_custom:
        try:
            config = customrules.load(args.rules)
        except Exception as exc:
            print(f"自定义规则加载失败，已忽略：{exc}", file=sys.stderr)
    result = engine.run(path, min_severity=min_severity, config=config)

    if not args.quiet:
        print(report.console(result))
        print()
        print(report.rule_table(result))

    if args.md:
        args.md.write_text(report.markdown(result), encoding="utf-8")
        print(f"\nMarkdown 报告：{args.md}")
    if args.json:
        report.dump_json(result, args.json)
        print(f"JSON 结果：{args.json}")

    if args.semantic:
        key = llm.load_key()
        if not key:
            print("\n未配置 API Key，已跳过语义检查")
        else:
            print("\n语义检查中…")
            issues, raw = llm.semantic_issues(result.doc, llm.LLMConfig(api_key=key))
            result.issues.extend(issues)
            print(f"语义检查新增 {len(issues)} 条" if issues else "语义检查未发现新问题")
            if raw.get("error"):
                print(f"  （模型调用失败：{raw['error'][:120]}）")

    if args.db:
        task_id = store.save_result(result, args.db)
        if config is not None:
            store.sync_rules(config, args.db)
        print(f"已写入数据库 task#{task_id}")

    if args.fix:
        targets = result.fixable
        if not targets:
            print("\n没有可自动修复的项")
            return 1 if result.counts["错误"] else 0
        changes = fixer.preview(result.doc, targets)
        print(f"\n将修改 {len(changes)} 处：")
        for change in changes[:20]:
            print("  " + change.as_row())
        if len(changes) > 20:
            print(f"  ... 其余 {len(changes) - 20} 处")
        if not args.yes:
            answer = input("\n确认写入？原文件会先备份 [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                print("已取消，未修改任何文件")
                return 0
        backup_path, applied = fixer.apply(path, targets)
        print(f"已备份：{backup_path.name}")
        print(f"已修复 {len(applied)} 处，重新检查：")
        again = engine.run(path, Policy())
        print(f"  错误 {again.counts['错误']} · 警告 {again.counts['警告']} · 提示 {again.counts['提示']}")
        return 0

    return 1 if result.counts["错误"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
