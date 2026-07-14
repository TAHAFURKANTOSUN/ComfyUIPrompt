@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (set "PY=python") else (set "PY=py -3")

echo Bagimliliklar kontrol ediliyor...
%PY% -m pip install -r backend\requirements.txt --quiet --disable-pip-version-check

echo.
echo Sunucu baslatiliyor: http://127.0.0.1:8765
echo (Kapatmak icin bu pencerede Ctrl+C)
echo.
%PY% -m backend.main

pause
