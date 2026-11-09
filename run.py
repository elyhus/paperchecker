# -*- coding: utf-8 -*-
"""统一入口：

    python run.py                       # 打开桌面界面
    python run.py check 文档.docx        # 命令行检查
    python run.py check 文档.docx --fix  # 命令行修复
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] in {"check", "batch", "rules", "history"}:
        from paperchecker.cli import main as cli_main
        raise SystemExit(cli_main(argv))
    from paperchecker.gui import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
