@echo off
REM ============================================================
REM  NOLAN WebUI launcher
REM  - Render service  : http://127.0.0.1:3010
REM  - NOLAN Hub (UI)   : http://127.0.0.1:8011  (8001 is SPARTA's)
REM  Each service opens in its own window; close a window to stop it.
REM ============================================================

set "ROOT=%~dp0"
set "PYEXE=D:\env\nolan\python.exe"

REM Run Python in UTF-8 mode (-X utf8) so Chinese/Unicode filenames, subtitles and
REM ffmpeg subprocess output are decoded as UTF-8. Without this, Windows uses the
REM legacy cp1252 codec, which crashes ffmpeg's output reader and corrupts scene
REM detection (fewer segments). The -X flag is more reliable than the env var.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo Building and starting NOLAN render service on http://127.0.0.1:3010 ...
start "NOLAN Render Service" cmd /k "cd /d "%ROOT%render-service" && npm run build && node dist\server.js"

echo Starting NOLAN Hub on http://127.0.0.1:8011 ...
start "NOLAN Hub" cmd /k "cd /d "%ROOT%" && "%PYEXE%" -X utf8 -c "from nolan.cli import main; main()" hub --host 127.0.0.1 --port 8011"

echo.
echo NOLAN is starting up in two new windows.
echo   Hub UI         : http://127.0.0.1:8011
echo   Render service : http://127.0.0.1:3010
echo.
echo Opening the Hub in your browser...
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8011
