@echo off
REM ============================================================
REM  NOLAN WebUI launcher
REM  - Render service  : http://127.0.0.1:3010
REM  - NOLAN Hub (UI)   : http://127.0.0.1:8011  (8001 is SPARTA's)
REM  Each service opens in its own window; close a window to stop it.
REM
REM  Tailscale access: the Hub is exposed to the tailnet via a one-time
REM  "tailscale serve" TCP proxy (set up out-of-band), which forwards
REM  tailnet :8011 -> 127.0.0.1:8011. The Hub therefore only needs to bind
REM  loopback here. Reachable on the tailnet at http://<tailscale-ip>:8011.
REM  To inspect/disable: tailscale serve status / tailscale serve --tcp=8011 off
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

echo Starting NOLAN Hub on http://127.0.0.1:8011 (tailnet via tailscale serve) ...
start "NOLAN Hub" cmd /k "cd /d "%ROOT%" && "%PYEXE%" -X utf8 -c "from nolan.cli import main; main()" hub --host 127.0.0.1 --port 8011"

REM Expose the Hub on the tailnet: tailnet :8011 -> 127.0.0.1:8011.
REM Idempotent (re-running replaces the existing serve config). Survives reboots.
set "TSEXE=C:\Program Files\Tailscale\tailscale.exe"
if exist "%TSEXE%" (
  echo Configuring Tailscale serve so http://^<tailscale-ip^>:8011 reaches the Hub ...
  "%TSEXE%" serve --bg --tcp=8011 tcp://127.0.0.1:8011
) else (
  echo [warn] tailscale.exe not found at "%TSEXE%" - skipping tailnet exposure.
)

echo.
echo NOLAN is starting up in two new windows.
echo   Hub UI         : http://127.0.0.1:8011
echo   Render service : http://127.0.0.1:3010
echo.
echo Opening the Hub in your browser...
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8011
