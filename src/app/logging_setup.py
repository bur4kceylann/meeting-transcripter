"""Dönen log dosyası ve yakalanmamış hataların kaydı.

Kullanıcıya teknik ayrıntı gösterilmez; tüm ayrıntı buraya yazılır ve menüdeki
"Hata Kaydını Göster" ile bu klasör açılır.
"""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path) -> logging.Handler:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "transkript.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    def _log_uncaught(exc_type, exc, tb):
        root.critical("Yakalanmamış hata", exc_info=(exc_type, exc, tb))

    def _log_thread(args):
        root.critical("Thread hatası (%s)", args.thread.name if args.thread else "?",
                      exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = _log_uncaught
    threading.excepthook = _log_thread
    return handler
