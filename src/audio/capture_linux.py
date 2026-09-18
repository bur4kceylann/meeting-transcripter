"""Linux sistem sesi yakalama — PulseAudio / PipeWire "monitor" kaynağı.

PulseAudio ve PipeWire, her çıkış aygıtı için sesin kopyasını veren bir
".monitor" giriş kaynağı sunar. sounddevice üzerinden bu kaynak bir giriş
cihazı gibi açılır; ek kurulum çoğu dağıtımda gerekmez.
"""

from __future__ import annotations

import numpy as np
import sounddevice as sd

_HELP = (
    "Monitor ses kaynağı bulunamadı.\n"
    "PulseAudio/PipeWire çalışıyor mu kontrol et: `pactl list sources short`\n"
    "Çıktıda '.monitor' ile biten bir kaynak görünmeli."
)


class DeviceNotFoundError(RuntimeError):
    pass


def _find_monitor_device() -> int:
    candidates = []
    for idx, dev in enumerate(sd.query_devices()):
        name = dev["name"].lower()
        if dev["max_input_channels"] > 0 and ("monitor" in name or name == "pulse"):
            candidates.append((idx, name))
    # Doğrudan '.monitor' kaynağını tercih et; yoksa 'pulse' aygıtına düş
    # (pulse aygıtı, PulseAudio'da varsayılan kaynağa bağlanır).
    for idx, name in candidates:
        if "monitor" in name:
            return idx
    if candidates:
        return candidates[0][0]
    raise DeviceNotFoundError(_HELP)


class LinuxCapture:
    def __init__(self) -> None:
        self._device_index = _find_monitor_device()
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
        if audio.ndim == 2:
            audio = audio.mean(axis=1)
        return audio.astype(np.float32)
