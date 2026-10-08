@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

REM ---- need administrator rights (the game runs elevated) ----
net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Requesting administrator rights ...
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b
)

echo ==========================================
echo    IDV Piano Assist  V1
echo ==========================================
echo    F7 = calibrate overlay
echo    F8 = start / stop
echo    F9 = restart
echo.

REM ---- pick whichever python is available ----
if exist "%~dp0.venv\Scripts\python.exe" goto use_venv
if exist "%USERPROFILE%\.cherrystudio\bin\uv.exe" goto use_csuv
where uv >nul 2>&1 && goto use_uv
where python >nul 2>&1 && goto use_py

echo [ERROR] None of these worked:
echo   1. .venv\Scripts\python.exe
echo   2. %%USERPROFILE%%\.cherrystudio\bin\uv.exe
echo   3. uv in PATH
echo   4. python in PATH
set RC=1
goto finished

:use_venv
echo [env] local .venv
"%~dp0.venv\Scripts\python.exe" "%~dp0main.py"
set RC=%errorlevel%
goto finished

:use_csuv
echo [env] cherrystudio uv
"%USERPROFILE%\.cherrystudio\bin\uv.exe" run python "%~dp0main.py"
set RC=%errorlevel%
goto finished

:use_uv
echo [env] uv in PATH
uv run python "%~dp0main.py"
set RC=%errorlevel%
goto finished

:use_py
echo [env] system python
python "%~dp0main.py"
set RC=%errorlevel%
goto finished

:finished
echo.
echo ---------------- exited (code %RC%) ----------------
echo If it closed by itself, screenshot the text above.
pause
