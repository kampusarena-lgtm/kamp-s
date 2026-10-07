@echo off
setlocal EnableExtensions
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0KURULUM_V4.ps1"
set "RESULT=%errorlevel%"
if not "%RESULT%"=="0" echo Kurulum tamamlanamadi. Yukaridaki hata mesajini kontrol edin.
pause
exit /b %RESULT%
