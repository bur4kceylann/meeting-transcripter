"""Windows sistem sesi yakalama — WASAPI loopback (ek sürücü gerekmez).

`soundcard` kütüphanesi, varsayılan hoparlörü loopback modunda bir mikrofon
gibi açarak sistemden çıkan sesi verir. Kayıt, stop() çağrılana kadar ayrı bir
thread'de küçük bloklar halinde okunur.
"""

from __future__ import annotations

import threading

import numpy as np

_SAMPLERATE = 48_000
_BLOCKSIZE = 4_800  # 100 ms


class WindowsCapture:
    def __init__(self) -> None:
        import soundcard as sc  # OS'a özgü import, modül içinde tutuluyor

        speaker = sc.default_speaker()
        self._mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        self._device_name = speaker.name
        self.samplerate = _SAMPLERATE
        self.channels = 2
        self._chunks: list[np.ndarray] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def device_hint(self) -> str:
        return f"{self._device_name} (WASAPI loopback) @ {self.samplerate} Hz"

    def _record_loop(self) -> None:
        with self._mic.recorder(samplerate=self.samplerate, channels=self.channels) as rec:
            while not self._stop_event.is_set():
                self._chunks.append(rec.record(numframes=_BLOCKSIZE))

    def start(self) -> None:
        self._chunks = []
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

    def stop(self) -> np.ndarray:
        if self._thread is None:
            raise RuntimeError("start() çağrılmadan stop() çağrıldı")
        self._stop_event.set()
        self._thread.join(timeout=5)
        self._thread = None
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(self._chunks, axis=0)
        self._chunks = []
        if audio.ndim == 2:
            audio = audio.mean(axis=1)
        return audio.astype(np.float32)
