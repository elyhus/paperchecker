#!/bin/zsh
# 双击运行：启动 PaperChecker 桌面界面
# 也可以把某个 .docx 文件拖到这个图标上，直接检查它。
cd "$(dirname "$0")" || exit 1

PY="/Users/kawen/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi

if ! "$PY" -c "import docx" >/dev/null 2>&1; then
  echo "找不到 python-docx，无法启动。"
  echo "请确认上面的 Python 路径存在，或先安装： $PY -m pip install python-docx"
  echo
  read -r "?按回车关闭窗口..."
  exit 1
fi

echo "正在启动 PaperChecker…（关闭这个终端窗口不会退出程序，请直接关掉程序窗口）"
exec "$PY" run.py "$@"
