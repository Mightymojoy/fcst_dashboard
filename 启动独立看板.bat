@echo off
chcp 65001 >nul
echo 正在更新数据并生成独立看板...
cd /d "%~dp0\forecast_system"
python export_web_json.py
cd /d "%~dp0"
python build_standalone.py
echo.
echo 生成完成！打开 fcst_dashboard.html 即可查看
pause