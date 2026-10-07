"""macOS sistem sesi yakalama: Core Audio Process Tap (macOS 14.4+, sürücü gerekmez).

Ses, `audio_tap` yardımcısı (tools/audio_tap.swift) tarafından yakalanır ve
stdout'undan ham float32 interleaved PCM olarak okunur. Kullanıcının ses
çıkışı değişmez. İlk kayıtta macOS "sistem sesi kaydı" izni ister.

Yardımcı kayıt sırasında çıkarsa (ses çıkışı değişti, ör. AirPods takıldı;
ya da çöktü) yeniden başlatılır ve kayıt kesintisiz devam eder; yeni cihazın
örnekleme hızı farklıysa ses ilk hıza dönüştürülür. Yeniden başlatma da
başarısız olursa `on_interrupted` çağrılır; o ana kadarki ses korunur.

Bellek için ses okunurken mono'ya indirilir (1 saatlik 48 kHz kayıt ~690 MB).
"""

from __future__ import annotations

import json
import logging
import select
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .platform_detect import CapturePermissionError

log = logging.getLogger(__name__)

_PERMISSION_EXIT_CODE = 77
_READ_SIZE = 64 * 1024
_HEADER_TIMEOUT = 10.0  # sn; coreaudiod takılırsa menü çubuğu donmasın
_RESTART_ATTEMPTS = 3
_RESTART_DELAY = 0.5  # sn; cihaz değişiminin oturması için


def _default_helper() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller paketi: Contents/Frameworks
        return Path(sys._MEIPASS) / "audio_tap"
    return Path(__file__).resolve().parents[2] / "tools" / "audio_tap"


def _resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or audio.size == 0:
        return audio
    n_out = int(round(audio.size * dst_rate / src_rate))
    src_t = np.arange(audio.size) / src_rate
    dst_t = np.arange(n_out) / dst_rate
    return np.interp(dst_t, src_t, audio).astype(np.float32)


def _close_pipes(proc: subprocess.Popen) -> None:
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        if stream is not None:
            stream.close()


class MacOSCapture:
    def __init__(self, helper: str | Path | None = None) -> None:
        self._helper = Path(helper) if helper else _default_helper()
        if not self._helper.exists():
            raise FileNotFoundError(
                f"audio_tap bulunamadı: {self._helper}\n"
                "Derle: swiftc -O -target arm64-apple-macos14.4 tools/audio_tap.swift -o tools/audio_tap"
            )
        self.samplerate = 48_000
        self.channels = 2
        # Yardımcı yeniden başlatılamazsa okuma thread'inden çağrılır.
        self.on_interrupted: Callable[[], None] | None = None
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._stopping = False
        self._chunks: list[np.ndarray] = []

    def device_hint(self) -> str:
        return f"Sistem sesi (Core Audio Process Tap) @ {self.samplerate} Hz, {self.channels} kanal"

    def _spawn(self) -> tuple[subprocess.Popen, int, int]:
        """Yardımcıyı başlatır, başlığını okur: (süreç, örnekleme hızı, kanal)."""
        proc = subprocess.Popen(
            [str(self._helper)],
            stdin=subprocess.PIPE,  # açık tutulur; kapanınca yardımcı kendini temizler
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        ready, _, _ = select.select([proc.stderr], [], [], _HEADER_TIMEOUT)
        header = proc.stderr.readline() if ready else b""
        try:
            fmt = json.loads(header)
            return proc, int(fmt["samplerate"]), int(fmt["channels"])
        except (ValueError, KeyError, TypeError):
            pass
        if not ready:
            proc.kill()
        try:
            code = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = proc.wait()
        message = (header + proc.stderr.read()).decode(errors="replace").strip()
        _close_pipes(proc)
        if not ready:
            raise RuntimeError(f"audio_tap {_HEADER_TIMEOUT:g} sn içinde yanıt vermedi")
        if code == _PERMISSION_EXIT_CODE:
            raise CapturePermissionError(message or "sistem sesi izni verilmedi")
        raise RuntimeError(f"audio_tap başlatılamadı (kod {code}): {message}")

    def start(self) -> None:
        self._chunks = []
        self._stopping = False
        proc, self.samplerate, self.channels = self._spawn()
        self._proc = proc
        self._reader = threading.Thread(
            target=self._read_loop, args=(proc, self.samplerate, self.channels), daemon=True
        )
        self._reader.start()

    def _drain(self, proc: subprocess.Popen, rate: int, channels: int) -> None:
        frame_bytes = 4 * channels
        pending = b""
        while chunk := proc.stdout.read1(_READ_SIZE):
            data = pending + chunk
            usable = len(data) - len(data) % frame_bytes
            pending = data[usable:]
            if usable:
                frames = np.frombuffer(data[:usable], dtype="<f4").reshape(-1, channels)
                mono = frames.mean(axis=1, dtype=np.float32)
                self._chunks.append(_resample(mono, rate, self.samplerate))

    def _read_loop(self, proc: subprocess.Popen, rate: int, channels: int) -> None:
        while True:
            self._drain(proc, rate, channels)
            code = proc.wait()
            _close_pipes(proc)
            with self._lock:
                if self._stopping:
                    return
            log.warning("audio_tap kayıt sırasında çıktı (kod %s); yeniden başlatılıyor", code)
            restarted = self._restart()
            if restarted is None:
                log.error("audio_tap yeniden başlatılamadı; kayıt kesildi")
                if self.on_interrupted:
                    self.on_interrupted()
                return
            proc, rate, channels = restarted

    def _restart(self) -> tuple[subprocess.Popen, int, int] | None:
        for attempt in range(1, _RESTART_ATTEMPTS + 1):
            time.sleep(_RESTART_DELAY)
            try:
                proc, rate, channels = self._spawn()
            except Exception:
                log.warning("audio_tap yeniden başlatma denemesi %d başarısız", attempt, exc_info=True)
                continue
            with self._lock:
                if self._stopping:  # bu arada stop() çağrıldı
                    proc.kill()
                    proc.wait()
                    _close_pipes(proc)
                    return None
                self._proc = proc
            log.info("audio_tap yeniden başladı: %d Hz, %d kanal", rate, channels)
            return proc, rate, channels
        return None

    def stop(self) -> np.ndarray:
        if self._reader is None:
            raise RuntimeError("start() çağrılmadan stop() çağrıldı")
        with self._lock:
            self._stopping = True
            proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if threading.current_thread() is not self._reader:
            self._reader.join(timeout=10)
        self._reader = None
        self._proc = None
        chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32, copy=False)
