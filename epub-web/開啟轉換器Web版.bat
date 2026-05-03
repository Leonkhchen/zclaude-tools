@echo off
chcp 65001 >nul
echo =============================================
echo  EPUB / PDF 轉換器  (Web 版)
echo  http://localhost:5000
echo =============================================
echo.

cd /d "%~dp0"

REM 安裝依賴（若尚未安裝）
pip show flask >nul 2>&1 || (
    echo 正在安裝 Python 套件...
    pip install -r requirements.txt
    echo.
)

echo 啟動中，請稍候...
echo 請在瀏覽器開啟：http://localhost:5000
echo 按 Ctrl+C 可停止伺服器
echo.

python app.py
pause
