@echo off
setlocal EnableExtensions
set "VBS=%~dp0KAMPUS_GAME_ARENA_GIZLI_BASLAT.vbs"
set "LOG=%~dp0kurulum-sonucu.txt"
net session >nul 2>&1
if errorlevel 1 (
 echo Yonetici olarak calistirin.
 pause
 exit /b 1
)
call "%~dp0KAMPUS_GAME_ARENA_KILIT_V5.bat" -Kontrol >"%LOG%" 2>&1
if errorlevel 1 (
 type "%LOG%"
 echo Kontrol basarisiz. Gorev kurulmadigi icin hata duzeltildikten sonra tekrar deneyin.
 pause
 exit /b 1
)
schtasks /Create /TN "KampusGameArena_KilitEkrani" /SC ONSTART /RU SYSTEM /RL HIGHEST /TR "wscript.exe \"%VBS%\"" /F >>"%LOG%" 2>&1
if errorlevel 1 (
 type "%LOG%"
 echo Kurulum basarisiz.
 pause
 exit /b 1
)
REM Disable only the V4 task created by our previous installer, if present.
schtasks /Query /TN "KampusArena_Kilit_V4" >nul 2>&1
if not errorlevel 1 schtasks /Change /TN "KampusArena_Kilit_V4" /Disable >>"%LOG%" 2>&1
call "%~dp0KAMPUS_GAME_ARENA_KILIT_V5.bat" >>"%LOG%" 2>&1
if errorlevel 1 (
 type "%LOG%"
 echo Gorev kuruldu fakat ilk gorsel degisikligi basarisiz. Mevcut kilit.png korunur.
 pause
 exit /b 2
)
type "%LOG%"
echo Kurulum tamamlandi. kilit.png guncellendi. Her acilista gizli calisacak.
pause
exit /b 0
