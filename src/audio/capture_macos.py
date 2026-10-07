"""macOS sistem sesi yakalama: Core Audio Process Tap (macOS 14.4+, sürücü gerekmez).

Ses, `audio_tap` yardımcısı (tools/audio_tap.swift) tarafından yakalanır ve
stdout'undan ham float32 interleaved PCM olarak okunur. Kullanıcının ses
çıkışı değişmez. İlk kayıtta macOS "sistem sesi kaydı" izni ister.

Bellek için ses okunurken mono'ya indirilir (1 saatlik 48 kHz kayıt ~690 MB).
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np

from .platform_detect import CapturePermissionError

_PERMISSION_EXIT_CODE = 77
_READ_SIZE = 64 * 1024


def _default_helper() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller paketi: Contents/Frameworks
        return Path(sys._MEIPASS) / "audio_tap"
    return Path(__file__).resolve().parents[2] / "tools" / "audio_tap"


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
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._chunks: list[np.ndarray] = []

    def device_hint(self) -> str:
        return f"Sistem sesi (Core Audio Process Tap) @ {self.samplerate} Hz, {self.channels} kanal"

    def start(self) -> None:
        self._chunks = []
        proc = subprocess.Popen(
            [str(self._helper)],
            stdin=subprocess.PIPE,  # açık tutulur; kapanınca yardımcı kendini temizler
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        header = proc.stderr.readline()
        try:
            fmt = json.loads(header)
        except ValueError:
            code = proc.wait(timeout=5)
            message = (header + proc.stderr.read()).decode(errors="replace").strip()
            if code == _PERMISSION_EXIT_CODE:
                raise CapturePermissionError(message or "sistem sesi izni verilmedi") from None
            raise RuntimeError(f"audio_tap başlatılamadı (kod {code}): {message}") from None
        self.samplerate = int(fmt["samplerate"])
        self.channels = int(fmt["channels"])
        self._proc = proc
        self._reader = threading.Thread(target=self._read_loop, args=(proc,), daemon=True)
        self._reader.start()

    def _read_loop(self, proc: subprocess.Popen) -> None:
        frame_bytes = 4 * self.channels
        pending = b""
        while chunk := proc.stdout.read1(_READ_SIZE):
            data = pending + chunk
            usable = len(data) - len(data) % frame_bytes
            pending = data[usable:]
            if usable:
                frames = np.frombuffer(data[:usable], dtype="<f4").reshape(-1, self.channels)
                self._chunks.append(frames.mean(axis=1, dtype=np.float32))

    def stop(self) -> np.ndarray:
        if self._proc is None:
            raise RuntimeError("start() çağrılmadan stop() çağrıldı")
        proc, self._proc = self._proc, None
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        self._reader.join(timeout=5)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            stream.close()
        chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32, copy=False)
