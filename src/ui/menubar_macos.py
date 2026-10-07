"""macOS menü çubuğu uygulaması: Controller'ın ince gösterim kabuğu (rumps).

Çalıştırma (kaynaktan):  .venv/bin/python src/ui/menubar_macos.py
Paketli uygulamada giriş noktası packaging/entry_macos.py'dir.
"""

from __future__ import annotations

import logging
import queue
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import rumps  # noqa: E402

from src import __version__  # noqa: E402
from src.app.controller import Controller, Phase, State  # noqa: E402
from src.app.logging_setup import setup_logging  # noqa: E402
from src.app.model_manager import ModelManager  # noqa: E402
from src.app.paths import AppPaths, resolve  # noqa: E402
from src.audio.platform_detect import get_capture_class  # noqa: E402
from src.ui import macos_system  # noqa: E402
from src.ui.status_text import quit_confirmation, status_title, toggle_label  # noqa: E402

log = logging.getLogger(__name__)

_PERMISSION_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_AudioCapture"
_SILENCE_HINT = "Ses çalıyorduysa menüden 'Sistem Sesi İznini Aç…' ile izni kontrol et."
_LOGIN_MARKER = "login_item_initialized"


class _QueueListener:
    """Controller olaylarını (worker thread'lerinden) ana thread'e taşır."""

    def __init__(self) -> None:
        self.events: queue.Queue = queue.Queue()

    def on_state(self, state: State) -> None:
        self.events.put(("state", state))

    def on_message(self, title: str, body: str) -> None:
        self.events.put(("message", (title, body)))

    def on_transcript_ready(self, txt_path: Path) -> None:
        self.events.put(("ready", txt_path))


def _engine_factory(model_dir: Path):
    from src.transcribe.whisper_engine import WhisperEngine

    return WhisperEngine(model_size=str(model_dir), compute_type="int8_float32")


class TranscriptApp(rumps.App):
    def __init__(self, paths: AppPaths) -> None:
        super().__init__("Transkript", title="🎙", quit_button=None)
        self._paths = paths
        self._listener = _QueueListener()
        self._state = State(Phase.NEEDS_MODEL)
        self._controller = Controller(
            capture_factory=get_capture_class(),
            engine_factory=_engine_factory,
            model_manager=ModelManager(paths.models),
            output_dir=paths.output,
            fallback_dir=paths.recovery,
            listener=self._listener,
            silence_hint=_SILENCE_HINT,
        )

        self.toggle_item = rumps.MenuItem("Kaydı Başlat", callback=self._on_toggle)
        self.retry_item = rumps.MenuItem("Tekrar Dene")
        self.login_item = rumps.MenuItem("Oturum Açıldığında Başlat")
        self.menu = [
            self.toggle_item,
            self.retry_item,
            None,
            rumps.MenuItem("Son Transkripti Aç", callback=self._on_open_last),
            rumps.MenuItem("Transkript Klasörünü Aç", callback=self._on_open_dir),
            None,
            self.login_item,
            rumps.MenuItem("Sistem Sesi İznini Aç…", callback=lambda _: macos_system.open_url(_PERMISSION_URL)),
            rumps.MenuItem("Hata Kaydını Göster", callback=lambda _: macos_system.open_path(paths.logs)),
            None,
            rumps.MenuItem(f"Transkript {__version__}"),
            rumps.MenuItem("Çıkış", callback=self._on_quit),
        ]
        self._init_login_item()
        macos_system.setup_notifications()
        rumps.Timer(self._on_tick, 0.25).start()
        self._controller.start()

    # --- oturum açılışında başlat ---

    def _init_login_item(self) -> None:
        if not macos_system.login_item_supported():
            self.login_item.title = "Oturum Açıldığında Başlat (yalnızca kurulu uygulamada)"
            return
        marker = self._paths.state / _LOGIN_MARKER
        if not marker.exists():  # ilk açılış: varsayılan olarak açık
            macos_system.set_login_item(True)
            marker.touch()
        self.login_item.state = int(macos_system.login_item_enabled())
        self.login_item.set_callback(self._on_login_item)

    def _on_login_item(self, sender) -> None:
        if macos_system.set_login_item(not sender.state):
            sender.state = int(macos_system.login_item_enabled())

    # --- menü olayları ---

    def _on_toggle(self, _sender) -> None:
        self._controller.toggle()

    def _on_retry(self, _sender) -> None:
        self._controller.retry_download()

    def _on_open_last(self, _sender) -> None:
        latest = self._controller.latest_transcript()
        if latest:
            macos_system.open_path(latest)
        else:
            macos_system.notify("Transkript yok", "Henüz üretilmiş bir transkript bulunamadı.")

    def _on_open_dir(self, _sender) -> None:
        try:
            self._paths.output.mkdir(parents=True, exist_ok=True)
            macos_system.open_path(self._paths.output)
        except OSError:
            log.exception("Transkript klasörü açılamadı")
            macos_system.open_path(self._paths.recovery if self._paths.recovery.exists() else self._paths.state)

    def _on_quit(self, _sender) -> None:
        confirm = quit_confirmation(self._state)
        if confirm and confirm.stop_button:
            # rumps.alert: ok=1, cancel=0, other=-1
            answer = rumps.alert(title=confirm.title, message=confirm.message,
                                 ok=confirm.stop_button, cancel="Vazgeç", other="Yine de Çık")
            if answer == 1:
                self._controller.toggle()  # durdur ve metne çevir; uygulama açık kalır
                return
            if answer == 0:
                return
        elif confirm:
            if rumps.alert(title=confirm.title, message=confirm.message, ok="Çık", cancel="Vazgeç") != 1:
                return
        self._controller.shutdown()
        rumps.quit_application()

    # --- ana thread döngüsü ---

    def _on_tick(self, _timer) -> None:
        while True:
            try:
                kind, payload = self._listener.events.get_nowait()
            except queue.Empty:
                break
            if kind == "state":
                self._apply_state(payload)
            elif kind == "message":
                macos_system.notify(*payload)
            elif kind == "ready":
                macos_system.notify("Transkript hazır", payload.name)
                macos_system.open_path(payload)
        self.title = status_title(self._state, time.monotonic())

    def _apply_state(self, state: State) -> None:
        self._state = state
        self.toggle_item.title = toggle_label(state)
        self.retry_item.set_callback(self._on_retry if state.phase is Phase.ERROR else None)


def main() -> None:
    paths = resolve()
    setup_logging(paths.logs)  # önce log: sonraki her hata kayda geçsin
    log.info("Transkript %s başlıyor (paketli: %s)", __version__, getattr(sys, "frozen", False))
    paths.ensure()
    TranscriptApp(paths).run()


if __name__ == "__main__":
    main()
