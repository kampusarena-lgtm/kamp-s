@echo off
setlocal EnableExtensions
if not exist "%~dp0KAMPUS_GAME_ARENA_KILIT_V4.ps1" exit /b 11
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0KAMPUS_GAME_ARENA_KILIT_V4.ps1" %*
exit /b %errorlevel%
