@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=py -3"
where py >nul 2>nul || set "PY=python"

%PY% -c "import docx" >nul 2>nul
if errorlevel 1 (
    echo 没有找到 python-docx，无法启动。
    echo 请先执行：  %PY% -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo 正在启动 PaperChecker...
%PY% run.py %*
if errorlevel 1 pause
