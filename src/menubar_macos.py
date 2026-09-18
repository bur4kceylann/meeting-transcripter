"""macOS menü çubuğu uygulaması.

Menü çubuğunda 🎙 simgesi durur; tıklayınca (veya klavye kısayolu
`.toggle_trigger` dosyasına dokununca) kayıt başlar, simge 🔴 + süre olur.
Tekrar tıklayınca kayıt durur, transkript arka planda üretilir, bitince
bildirim gösterilir ve .txt dosyası açılır.

Kayıt başlarken ses çıkışı otomatik "Hoparlör + BlackHole" multi-output
cihazına alınır, kayıt bitince önceki cihaza geri döndürülür (ses tuşları
normal zamanda çalışmaya devam eder).

Çalıştırma:  .venv/bin/python src/menubar_macos.py
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import rumps  # noqa: E402
import soundfile as sf  # noqa: E402

from src.audio.platform_detect import get_capture_class  # noqa: E402
from src.output.writer import write_srt, write_txt  # noqa: E402

_OUTPUT_DIR = _PROJECT_ROOT / "output"
_TRIGGER_FILE = _PROJECT_ROOT / ".toggle_trigger"
_AUDIO_ROUTE = _PROJECT_ROOT / "tools" / "audio_route"
_MODEL_SIZE = "medium"
_COMPUTE_TYPE = "int8_float32"  # CPU'da (Mac) desteklenen: int8, int8_float32, float32

IDLE, RECORDING, TRANSCRIBING = "idle", "recording", "transcribing"


def _notify(title: str, message: str) -> None:
    subprocess.run(
        ["osascript", "-e",
         f'display notification "{message}" with title "{title}"'],
        capture_output=True,
    )


def _audio_route(*args: str) -> str | None:
    """audio_route yardımcısını çalıştırır; stdout'u döndürür, hatada None."""
    try:
        proc = subprocess.run(
            [str(_AUDIO_ROUTE), *args], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


class TranscripterApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("🎙", quit_button=None)
        self.toggle_item = rumps.MenuItem("Kaydı Başlat", callback=self.on_toggle)
        self.open_last_item = rumps.MenuItem("Son Transkripti Aç", callback=self.on_open_last)
        self.open_dir_item = rumps.MenuItem("Çıktı Klasörünü Aç", callback=self.on_open_dir)
        self.quit_item = rumps.MenuItem("Çıkış", callback=self.on_quit)
        self.menu = [self.toggle_item, self.open_last_item, self.open_dir_item, None, self.quit_item]

        self._state = IDLE
        self._capture = None
        self._previous_output_uid: str | None = None
        self._record_started = 0.0
        self._engine = None  # ilk transkriptte yüklenir, sonra bellekte kalır
        self._last_txt: Path | None = None
        self._pending_message: tuple[str, str] | None = None  # worker → ana thread

        self._trigger_baseline = self._trigger_mtime()
        # Kısayol, uygulama kapalıyken basıldıysa (dosya son 3 sn içinde
        # dokunulmuşsa) açılışta kaydı hemen başlat.
        if self._trigger_baseline and time.time() - self._trigger_baseline < 3:
            rumps.Timer(self._start_on_launch, 1).start()

        rumps.Timer(self.on_tick, 0.5).start()

    # --- yardımcılar ---

    def _trigger_mtime(self) -> float:
        try:
            return _TRIGGER_FILE.stat().st_mtime
        except FileNotFoundError:
            return 0.0

    def _start_on_launch(self, timer) -> None:
        timer.stop()
        if self._state == IDLE:
            self._start_recording()

    # --- menü olayları ---

    def on_toggle(self, _sender=None) -> None:
        if self._state == IDLE:
            self._start_recording()
        elif self._state == RECORDING:
            self._stop_recording()
        else:
            _notify("Transkript sürüyor", "Önceki kayıt hâlâ metne çevriliyor, bekle.")

    def on_open_last(self, _sender) -> None:
        if self._last_txt and self._last_txt.exists():
            subprocess.run(["open", str(self._last_txt)])
        else:
            candidates = sorted(_OUTPUT_DIR.glob("*.txt")) if _OUTPUT_DIR.exists() else []
            if candidates:
                subprocess.run(["open", str(candidates[-1])])
            else:
                _notify("Transkript yok", "Henüz üretilmiş bir transkript bulunamadı.")

    def on_open_dir(self, _sender) -> None:
        _OUTPUT_DIR.mkdir(exist_ok=True)
        subprocess.run(["open", str(_OUTPUT_DIR)])

    def on_quit(self, _sender) -> None:
        if self._state == RECORDING:
            self._stop_recording()
        elif self._state == TRANSCRIBING:
            _notify("Transkript yarıda kaldı", "Ses dosyası diskte duruyor; transkript için main.py ile tekrar çalıştır.")
        rumps.quit_application()

    # --- periyodik kontrol (ana thread) ---

    def on_tick(self, _timer) -> None:
        # Klavye kısayolu tetikleyicisi
        mtime = self._trigger_mtime()
        if mtime > self._trigger_baseline:
            self._trigger_baseline = mtime
            self.on_toggle()

        # Worker thread'den gelen sonucu ana thread'de işle
        if self._pending_message is not None:
            title, message = self._pending_message
            self._pending_message = None
            _notify(title, message)

        # Başlık/simge güncelle
        if self._state == RECORDING:
            elapsed = int(time.monotonic() - self._record_started)
            self.title = f"🔴 {elapsed // 60:02d}:{elapsed % 60:02d}"
        elif self._state == TRANSCRIBING:
            self.title = "⏳"
        else:
            self.title = "🎙"

    # --- kayıt akışı ---

    def _start_recording(self) -> None:
        try:
            self._capture = get_capture_class()()
        except Exception as exc:
            _notify("Kayıt başlatılamadı", str(exc).splitlines()[0])
            return
        # Ses çıkışını multi-output'a al; önceki cihazı hatırla
        self._previous_output_uid = _audio_route("ensure")
        if self._previous_output_uid is None:
            _notify("Uyarı", "Ses çıkışı otomatik yönlendirilemedi; sesi duyduğundan emin ol.")
        self._capture.start()
        self._record_started = time.monotonic()
        self._state = RECORDING
        self.toggle_item.title = "Kaydı Durdur"
        _notify("Kayıt başladı", "Sistem sesi kaydediliyor. Durdurmak için simgeye tıkla.")

    def _stop_recording(self) -> None:
        samplerate = self._capture.samplerate
        audio = self._capture.stop()
        self._capture = None
        # Ses çıkışını eski cihaza geri al
        if self._previous_output_uid and "multi-output" not in self._previous_output_uid:
            _audio_route("set", self._previous_output_uid)

        if audio.size == 0 or float(abs(audio).max()) < 1e-4:
            self._state = IDLE
            self.toggle_item.title = "Kaydı Başlat"
            _notify("Boş kayıt", "Hiç ses yakalanmadı; transkript üretilmedi.")
            return

        # WAV'ı burada, ana thread'de senkron olarak yaz: Çıkış'a basılırsa bile
        # ses diske güvenle inmiş olur (yalnızca transkript yarıda kalabilir).
        _OUTPUT_DIR.mkdir(exist_ok=True)
        wav_path = _OUTPUT_DIR / f"kayit_{datetime.now():%Y%m%d_%H%M%S}.wav"
        sf.write(wav_path, audio, samplerate)

        self._state = TRANSCRIBING
        self.toggle_item.title = "Transkript üretiliyor..."
        threading.Thread(target=self._transcribe_worker, args=(wav_path,), daemon=True).start()

    def _transcribe_worker(self, wav_path: Path) -> None:
        try:
            if self._engine is None:
                from src.transcribe.whisper_engine import WhisperEngine

                self._engine = WhisperEngine(model_size=_MODEL_SIZE, compute_type=_COMPUTE_TYPE)

            result = self._engine.transcribe(wav_path)
            if not result.segments:
                self._pending_message = ("Transkript boş", "Kayıtta konuşma algılanamadı.")
                return

            txt_path = write_txt(result, wav_path.with_suffix(".txt"))
            write_srt(result, wav_path.with_suffix(".srt"))
            self._last_txt = txt_path
            self._pending_message = (
                "Transkript hazır",
                f"{txt_path.name} ({result.language}, {len(result.segments)} segment)",
            )
            subprocess.run(["open", str(txt_path)])
        except Exception as exc:
            self._pending_message = ("Transkript hatası", str(exc).splitlines()[0][:120])
        finally:
            self._state = IDLE
            self.toggle_item.title = "Kaydı Başlat"


if __name__ == "__main__":
    TranscripterApp().run()
