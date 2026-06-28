@echo off
REM ============================================================
REM  nolan.bat - UTF-8-safe NOLAN CLI wrapper
REM  Forwards all args to the installed nolan console script.
REM
REM  Why this exists: the generated nolan.exe shim does NOT set
REM  UTF-8 mode. Without it Windows uses legacy cp1252, which
REM  corrupts Chinese/Unicode filenames, subtitles and ffmpeg
REM  subprocess output (fewer scene segments). These vars force
REM  UTF-8 regardless of whether the conda env is activated.
REM
REM  Usage:  nolan <command> [args]
REM  e.g.    nolan hub --host 127.0.0.1 --port 8011
REM          nolan export ...
REM ============================================================

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"D:\env\nolan\Scripts\nolan.exe" %*
