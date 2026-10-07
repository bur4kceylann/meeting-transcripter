"""OS'u algılar ve uygun ses yakalama modülünü döndürür.

Her capture modülü aynı arayüz sözleşmesini sağlar:

    class Capture:
        samplerate: int          # yakalanan sesin örnekleme hızı (Hz)
        channels: int            # kanal sayısı
        def start(self) -> None  # kaydı başlat (bloklamaz)
        def stop(self) -> "np.ndarray"  # kaydı durdur, float32 mono ses döndür
        def device_hint(self) -> str    # kullanılan cihaz/kaynak açıklaması

Ortak kod (main.py, whisper_engine.py) OS bilmez; sadece bu sözleşmeyi kullanır.
"""

from __future__ import annotations

import platform


class UnsupportedPlatformError(RuntimeError):
    pass


class CapturePermissionError(RuntimeError):
    """İşletim sistemi sistem sesi yakalama iznini vermedi."""


def get_capture_class():
    """Çalışılan OS'a uygun Capture sınıfını döndürür."""
    system = platform.system()
    if system == "Darwin":
        from .capture_macos import MacOSCapture

        return MacOSCapture
    if system == "Windows":
        from .capture_windows import WindowsCapture

        return WindowsCapture
    if system == "Linux":
        from .capture_linux import LinuxCapture

        return LinuxCapture
    raise UnsupportedPlatformError(f"Desteklenmeyen platform: {system}")
