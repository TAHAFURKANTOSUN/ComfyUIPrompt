@echo off
setlocal
cd /d "%~dp0"

rem Bagimliliklar proje icindeki .venv sanal ortamina kurulur (sistem Pythonunu kirletmez).

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo Python bulunamadi. Python 3.10+ kurun: https://www.python.org/downloads/
  echo Kurulumda "Add python.exe to PATH" kutusunu isaretleyin.
  pause
  exit /b 1
)

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo Python 3.10 veya ustu gerekli.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Sanal ortam olusturuluyor ^(.venv^)...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Sanal ortam olusturulamadi.
    pause
    exit /b 1
  )
)

echo Bagimliliklar kontrol ediliyor...
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
  echo Bagimliliklar kurulamadi. Internet baglantinizi kontrol edin.
  pause
  exit /b 1
)

echo.
echo Sunucu baslatiliyor: http://127.0.0.1:8765
echo (Kapatmak icin bu pencerede Ctrl+C)
echo.
".venv\Scripts\python.exe" -m backend.main

pause
