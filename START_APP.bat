@echo off
echo ========================================
echo   Baseball Analytics App
echo ========================================
echo.
echo Starting Streamlit server...
echo.
cd /d "%~dp0"
start http://localhost:8501
python -m streamlit run app.py
pause