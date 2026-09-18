#!/bin/bash
# Kayıt aç/kapat tetikleyicisi — macOS Kısayollar'daki klavye kısayolu bunu çalıştırır.
# Menü çubuğu uygulaması çalışıyorsa kaydı başlatır/durdurur;
# çalışmıyorsa uygulamayı başlatır (uygulama açılır açılmaz kaydı başlatır).
set -e
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

touch "$PROJECT_DIR/.toggle_trigger"

if ! pgrep -f "src/menubar_macos.py" > /dev/null; then
    nohup "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/src/menubar_macos.py" \
        > /dev/null 2>&1 &
fi
