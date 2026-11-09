#!/usr/bin/env bash
# Linux 启动脚本：双击或 ./启动.sh
cd "$(dirname "$0")" || exit 1

PY="${PYTHON:-python3}"

if ! "$PY" -c "import docx" >/dev/null 2>&1; then
  echo "没有找到 python-docx，无法启动。"
  echo "请先执行： $PY -m pip install -r requirements.txt"
  echo "另外界面需要 tkinter：Debian/Ubuntu 上执行 sudo apt install python3-tk"
  exit 1
fi

exec "$PY" run.py "$@"
