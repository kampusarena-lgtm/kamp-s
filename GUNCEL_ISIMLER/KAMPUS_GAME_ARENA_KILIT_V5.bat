@echo off
setlocal EnableExtensions
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0KAMPUS_GAME_ARENA_KILIT_V5.ps1" %*
exit /b %errorlevel%
