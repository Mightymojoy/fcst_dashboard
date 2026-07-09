@echo off
chcp 65001 >nul
echo ============================================
echo   ITO FCST 看板 — 数据刷新与重建
echo ============================================
echo.

echo [1/4] 运行Transformer预测引擎（更新7-12月预测）...
cd /d "%~dp0\forecast_system"
python ts_transformer.py
if %errorlevel% neq 0 (
    echo [警告] Transformer预测异常，继续执行...
)

echo [2/4] 导出JSON数据...
python export_web_json.py
if %errorlevel% neq 0 (
    echo [错误] 数据导出失败！
    pause
    exit /b 1
)

echo [3/4] 重建独立看板HTML...
cd /d "%~dp0"
python build_standalone.py
if %errorlevel% neq 0 (
    echo [错误] 看板重建失败！
    pause
    exit /b 1
)

echo [4/4] 同步根目录index.html（GitHub Pages）...
copy /y "web\fcst_dashboard.html" "index.html" >nul

echo.
echo ============================================
echo   ✅ 全部完成！
echo   本地看板: web\fcst_dashboard.html
echo   GitHub Pages根目录已同步
echo   双击 fcst_dashboard.html 即可查看
echo ============================================
echo.
pause
