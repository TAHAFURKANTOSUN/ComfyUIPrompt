#!/usr/bin/env bash
# ComfyUI Prompt Asistanı — Linux/macOS başlatıcı
#
# Bağımlılıklar proje içindeki .venv sanal ortamına kurulur. Sistem Python'una
# doğrudan `pip install` yapmak yeni Debian/Ubuntu/Homebrew sürümlerinde
# "externally-managed-environment" (PEP 668) hatasıyla reddedilir.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Python 3 bulunamadi. Python 3.10+ kurun: https://www.python.org/downloads/" >&2
  exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Python 3.10 veya ustu gerekli (bulunan: $("$PY" --version 2>&1))." >&2
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Sanal ortam olusturuluyor (.venv)..."
  if ! "$PY" -m venv .venv; then
    echo "venv olusturulamadi. Debian/Ubuntu'da: sudo apt install python3-venv" >&2
    exit 1
  fi
fi

.venv/bin/python -m pip install -r backend/requirements.txt --quiet --disable-pip-version-check

echo
echo "Sunucu baslatiliyor: http://127.0.0.1:8765  (Ctrl+C ile kapatin)"
echo
exec .venv/bin/python -m backend.main
