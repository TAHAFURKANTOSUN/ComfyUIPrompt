#!/usr/bin/env bash
# ComfyUI Prompt Asistanı — Linux/macOS başlatıcı
set -e
cd "$(dirname "$0")"

python3 -m pip install -r backend/requirements.txt --quiet --disable-pip-version-check

echo
echo "Sunucu başlatılıyor: http://127.0.0.1:8765  (Ctrl+C ile kapatın)"
echo
python3 -m backend.main
