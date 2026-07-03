@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ===================
echo  ITO FCST 渠道预测看板
echo ===================
echo.

python "启动看板.py"

if errorlevel 1 (
    echo.
    echo [错误] 启动失败，请检查以上错误信息
    echo.
    pause
)
