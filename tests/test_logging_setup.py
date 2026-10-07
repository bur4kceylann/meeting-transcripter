import logging
import sys
import threading

from src.app.logging_setup import setup_logging


def test_writes_to_log_file(tmp_path, monkeypatch):
    # setup_logging süreç genelindeki hata kancalarını değiştirir; test sonrası geri yüklensin
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    handler = setup_logging(tmp_path / "logs")
    try:
        logging.getLogger("deneme").warning("Merhaba günlük")
        handler.flush()
        text = (tmp_path / "logs" / "transkript.log").read_text(encoding="utf-8")
        assert "Merhaba günlük" in text
        assert "WARNING" in text
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()
