"""macOS sistem sesi yakalama — BlackHole sanal ses sürücüsü üzerinden.

BlackHole, sistem çıkışına gönderilen sesi bir giriş cihazı olarak geri sunar.
Kullanıcının sesi hem duyup hem kaydedebilmesi için macOS'ta bir
"Multi-Output Device" (BlackHole + hoparlör) oluşturup çıkışı ona yönlendirmesi
gerekir. Kurulum: https://github.com/ExistentialAudio/BlackHole
"""

from __future__ import annotations

import numpy as np
import sounddevice as sd

_INSTALL_HELP = (
    "BlackHole ses sürücüsü bulunamadı.\n"
    "Kurulum:\n"
    "  1. brew install blackhole-2ch   (veya https://existential.audio/blackhole/)\n"
    "  2. macOS 'Audio MIDI Setup' uygulamasında bir Multi-Output Device oluştur\n"
    "     (BlackHole 2ch + kendi hoparlörün) ve sistem ses çıkışını ona yönlendir.\n"
    "  3. Bu aracı yeniden çalıştır."
)


class DeviceNotFoundError(RuntimeError):
    pass


def _find_blackhole_device() -> int:
    for idx, dev in enumerate(sd.query_devices()):
        if "blackhole" in dev["name"].lower() and dev["max_input_channels"] > 0:
            return idx
    raise DeviceNotFoundError(_INSTALL_HELP)


class MacOSCapture:
    def __init__(self) -> None:
        self._device_index = _find_blackhole_device()
        info = sd.query_devices(self._device_index)
        self._device_name = info["name"]
        self.samplerate = int(info["default_samplerate"])
        self.channels = min(2, info["max_input_channels"])
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None

    def device_hint(self) -> str:
        return f"{self._device_name} @ {self.samplerate} Hz, {self.channels} kanal"

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            # Overflow vb. durumlarda kaydı kesmeyip devam ediyoruz.
            print(f"[uyarı] ses akışı durumu: {status}")
        self._chunks.append(indata.copy())

    def start(self) -> None:
        self._chunks = []
        self._stream = sd.InputStream(
            device=self._device_index,
            channels=self.channels,
            samplerate=self.samplerate,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is None:
            raise RuntimeError("start() çağrılmadan stop() çağrıldı")
        self._stream.stop()
        self._stream.close()
        self._stream = None
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(self._chunks, axis=0)
        self._chunks = []
        # Whisper mono bekler; kanalları ortalayarak mono'ya indir.
        if audio.ndim == 2:
            audio = audio.mean(axis=1)
        return audio.astype(np.float32)
