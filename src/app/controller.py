"""OS ve arayüz bilmeyen uygulama çekirdeği.

Kabuk (macOS menü çubuğu, ileride Windows sistem tepsisi) yalnızca `toggle()`
gibi komutları çağırır ve `Listener` üzerinden gelen durum / mesajları
gösterir. Ağır işler (model indirme, transkript) arka planda çalışır;
Listener callback'leri o thread'lerden çağrılabilir, kabuk bunları kendi
ana thread'ine aktarmakla sorumludur.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Protocol

import numpy as np
import soundfile as sf

from src.app.model_manager import DiskFullError
from src.audio.platform_detect import CapturePermissionError
from src.output.writer import write_srt, write_txt
from src.transcribe.whisper_engine import TranscriptResult

log = logging.getLogger(__name__)

SILENCE_PEAK = 1e-4
_LOG_HINT = "Ayrıntılar için menüden 'Hata Kaydını Göster'."


class Phase(Enum):
    NEEDS_MODEL = "needs_model"
    DOWNLOADING = "downloading"
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    ERROR = "error"


class ErrorKind(Enum):
    NETWORK = "network"
    DISK = "disk"


@dataclass(frozen=True)
class State:
    phase: Phase
    progress: float | None = None  # DOWNLOADING / TRANSCRIBING: 0.0-1.0
    started_at: float | None = None  # RECORDING: clock() değeri
    error: ErrorKind | None = None  # ERROR


class Listener(Protocol):
    def on_state(self, state: State) -> None: ...
    def on_message(self, title: str, body: str) -> None: ...
    def on_transcript_ready(self, txt_path: Path) -> None: ...


class Capture(Protocol):
    samplerate: int

    def start(self) -> None: ...
    def stop(self) -> np.ndarray: ...


class Engine(Protocol):
    def transcribe(self, audio_path, language=None, on_progress=None) -> TranscriptResult: ...


def _run_in_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


class Controller:
    def __init__(
        self,
        *,
        capture_factory: Callable[[], Capture],
        engine_factory: Callable[[Path], Engine],
        model_manager,
        output_dir: Path,
        listener: Listener,
        silence_hint: str = "",
        run_in_background: Callable[[Callable[[], None]], None] = _run_in_thread,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._capture_factory = capture_factory
        self._engine_factory = engine_factory
        self._models = model_manager
        self._output_dir = output_dir
        self._listener = listener
        self._silence_hint = silence_hint
        self._run = run_in_background
        self._clock = clock
        self._now = now
        self._state = State(Phase.NEEDS_MODEL)
        self._capture: Capture | None = None
        self._engine: Engine | None = None
        self._last_transcript: Path | None = None

    @property
    def state(self) -> State:
        return self._state

    def _set(self, state: State) -> None:
        self._state = state
        self._listener.on_state(state)

    def _message(self, title: str, body: str) -> None:
        self._listener.on_message(title, body)

    # --- model ---

    def start(self) -> None:
        if self._models.is_ready():
            self._set(State(Phase.IDLE))
        else:
            self._begin_download()

    def retry_download(self) -> None:
        if self._state.phase in (Phase.ERROR, Phase.NEEDS_MODEL):
            self._begin_download()

    def _begin_download(self) -> None:
        self._set(State(Phase.DOWNLOADING, progress=0.0))
        self._run(self._download_worker)

    def _set_download_progress(self, progress: float) -> None:
        if self._state.phase is not Phase.DOWNLOADING:
            return
        # yalnızca tam yüzde değişince yayınla (1 MB'lık her parçada değil)
        if int(progress * 100) != int((self._state.progress or 0.0) * 100):
            self._set(State(Phase.DOWNLOADING, progress=progress))

    def _download_worker(self) -> None:
        try:
            self._models.download(self._set_download_progress)
        except DiskFullError:
            log.exception("Model indirilemedi: disk dolu")
            self._set(State(Phase.ERROR, error=ErrorKind.DISK))
            self._message("Diskte yeterli yer yok",
                          "Model için yaklaşık 2 GB boş alan gerekiyor. Yer açıp menüden 'Tekrar Dene'ye tıkla.")
            return
        except Exception:
            log.exception("Model indirilemedi")
            self._set(State(Phase.ERROR, error=ErrorKind.NETWORK))
            self._message("Model indirilemedi",
                          "İnternet bağlantını kontrol edip menüden 'Tekrar Dene'ye tıkla.")
            return
        log.info("Model hazır: %s", self._models.model_dir)
        self._set(State(Phase.IDLE))
        self._message("Hazır", "🎙 simgesine tıklayıp kayda başlayabilirsin.")

    # --- kayıt ---

    def toggle(self) -> None:
        phase = self._state.phase
        if phase is Phase.IDLE:
            self._start_recording()
        elif phase is Phase.RECORDING:
            self._stop_recording()
        elif phase is Phase.DOWNLOADING:
            pct = int((self._state.progress or 0.0) * 100)
            self._message("Model hazırlanıyor", f"Model indiriliyor (%{pct}). Bitince kayıt yapabilirsin.")
        elif phase is Phase.TRANSCRIBING:
            self._message("Transkript sürüyor", "Önceki kayıt hâlâ metne çevriliyor. Bitince yeni kayıt başlatabilirsin.")
        else:
            self._message("Model hazır değil", "Menüden 'Tekrar Dene' ile modeli indir.")

    def _start_recording(self) -> None:
        try:
            capture = self._capture_factory()
            capture.start()
        except CapturePermissionError:
            log.warning("Sistem sesi izni yok", exc_info=True)
            self._message("Sistem sesine izin verilmedi", "Menüden sistem sesi iznini açıp tekrar dene.")
            return
        except Exception:
            log.exception("Kayıt başlatılamadı")
            self._message("Kayıt başlatılamadı", f"Bir sorun oluştu. {_LOG_HINT}")
            return
        self._capture = capture
        log.info("Kayıt başladı")
        self._set(State(Phase.RECORDING, started_at=self._clock()))

    def _stop_recording(self) -> None:
        try:
            wav = self._save_recording()
        except Exception:
            log.exception("Kayıt durdurulamadı")
            self._set(State(Phase.IDLE))
            self._message("Bir sorun oluştu", f"Kayıt kaydedilemedi. {_LOG_HINT}")
            return
        if wav is None:
            return
        self._set(State(Phase.TRANSCRIBING, progress=0.0))
        self._run(lambda: self._transcribe_worker(wav))

    def _save_recording(self) -> Path | None:
        """Kaydı durdurur ve WAV'ı yazar. Sessizse None döner ve IDLE'a geçer."""
        capture, self._capture = self._capture, None
        audio = capture.stop()
        if audio.size == 0 or float(np.abs(audio).max()) < SILENCE_PEAK:
            log.info("Sessiz kayıt (%d örnek)", audio.size)
            self._set(State(Phase.IDLE))
            body = "Kayıt süresince bilgisayardan ses gelmedi."
            self._message("Kayıtta ses algılanmadı", f"{body} {self._silence_hint}".strip())
            return None
        self._output_dir.mkdir(parents=True, exist_ok=True)
        wav = self._output_dir / f"kayit_{self._now():%Y%m%d_%H%M%S}.wav"
        sf.write(wav, audio, capture.samplerate)
        log.info("Kayıt yazıldı: %s (%.1f sn)", wav, audio.size / capture.samplerate)
        return wav

    def _transcribe_worker(self, wav: Path) -> None:
        last_pct = 0

        def progress(p: float) -> None:
            nonlocal last_pct
            pct = int(p * 100)
            if pct != last_pct:
                last_pct = pct
                self._set(State(Phase.TRANSCRIBING, progress=p))

        try:
            if self._engine is None:
                self._engine = self._engine_factory(self._models.model_dir)
            result = self._engine.transcribe(wav, on_progress=progress)
            if not result.segments:
                self._message("Konuşma algılanamadı", "Kayıtta metne çevrilecek konuşma bulunamadı.")
                return
            txt = write_txt(result, wav.with_suffix(".txt"))
            write_srt(result, wav.with_suffix(".srt"))
            self._last_transcript = txt
            log.info("Transkript hazır: %s (%s, %d segment)", txt, result.language, len(result.segments))
            self._listener.on_transcript_ready(txt)
        except Exception:
            log.exception("Transkript üretilemedi: %s", wav)
            self._message("Bir sorun oluştu", f"Transkript üretilemedi; ses kaydı klasörde duruyor. {_LOG_HINT}")
        finally:
            self._set(State(Phase.IDLE))

    # --- diğer ---

    def shutdown(self) -> None:
        """Uygulama kapanırken çağrılır. Kayıt sürüyorsa ses diske yazılır (transkript edilmez)."""
        if self._state.phase is Phase.RECORDING:
            try:
                self._save_recording()
            except Exception:
                log.exception("Kapanışta kayıt kaydedilemedi")

    def latest_transcript(self) -> Path | None:
        if self._last_transcript and self._last_transcript.exists():
            return self._last_transcript
        if not self._output_dir.exists():
            return None
        candidates = sorted(self._output_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime)
        return candidates[-1] if candidates else None
