"""CLI giriş noktası.

Kullanım:
    python src/main.py                    # sistem sesini kaydet (Ctrl+C ile durdur), sonra transkript et
    python src/main.py toplanti.wav       # var olan bir ses dosyasını transkript et
    python src/main.py --model large-v3   # en yüksek doğruluk için daha büyük model
    python src/main.py --language tr      # dili elle sabitle (varsayılan: otomatik algıla)
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

# `python src/main.py` ile doğrudan çalıştırıldığında `src.` importları için
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.output.writer import write_srt, write_txt  # noqa: E402
from src.transcribe.whisper_engine import WhisperEngine  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="transcript-tool",
        description="Sistem sesini yakalayıp yerel olarak (offline) transkript eder.",
    )
    parser.add_argument(
        "audio_file",
        nargs="?",
        default=None,
        help="Transkript edilecek mevcut ses dosyası. Verilmezse sistem sesi kaydedilir.",
    )
    parser.add_argument(
        "--model",
        default="medium",
        help="Whisper model boyutu: tiny/base/small/medium/large-v3 (varsayılan: medium)",
    )
    parser.add_argument(
        "--compute-type",
        default="int8_float32",
        help=(
            "CTranslate2 hesaplama tipi (varsayılan: int8_float32). "
            "CPU'da (Mac dahil) geçerli değerler: int8, int8_float32, float32."
        ),
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Dil kodu (örn. tr, en). Verilmezse otomatik algılanır.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(_PROJECT_ROOT / "output"),
        help="Çıktı klasörü (varsayılan: output/)",
    )
    return parser.parse_args()


def _record_system_audio(output_dir: Path) -> Path:
    """Sistem sesini Ctrl+C'ye kadar kaydeder, WAV yolunu döndürür."""
    import soundfile as sf

    from src.audio.platform_detect import get_capture_class

    # Arka planda başlatılsa bile (shell SIGINT'i yok saydırır) Ctrl+C ve
    # SIGTERM ile temiz durdurma çalışsın: ikisi de KeyboardInterrupt üretir.
    def _stop_signal(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _stop_signal)
    signal.signal(signal.SIGTERM, _stop_signal)

    capture = get_capture_class()()
    print(f"Ses kaynağı: {capture.device_hint()}")
    print("Kayıt başladı. Durdurmak için Ctrl+C'ye bas.\n")

    is_tty = sys.stdout.isatty()
    capture.start()
    started = time.monotonic()
    try:
        while True:
            if is_tty:
                elapsed = int(time.monotonic() - started)
                print(
                    f"\r  kayıt süresi: {elapsed // 60:02d}:{elapsed % 60:02d}",
                    end="",
                    flush=True,
                )
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\nKayıt durduruluyor...")
    audio = capture.stop()

    if audio.size == 0:
        sys.exit("Hiç ses yakalanamadı. Ses çıkışının doğru cihaza yönlendirildiğinden emin ol.")

    duration = audio.size / capture.samplerate
    peak = float(abs(audio).max())
    if peak < 1e-4:
        print(
            "[uyarı] Kayıt tamamen sessiz görünüyor. macOS'ta sistem çıkışının "
            "BlackHole içeren Multi-Output Device'a yönlendirildiğini kontrol et."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = output_dir / f"kayit_{datetime.now():%Y%m%d_%H%M%S}.wav"
    sf.write(wav_path, audio, capture.samplerate)
    print(f"Kayıt kaydedildi: {wav_path} ({duration:.1f} sn)")
    return wav_path


def main() -> None:
    args = _parse_args()
    output_dir = Path(args.output_dir)

    if args.audio_file:
        audio_path = Path(args.audio_file)
        if not audio_path.exists():
            sys.exit(f"Dosya bulunamadı: {audio_path}")
    else:
        audio_path = _record_system_audio(output_dir)

    print(f"\nModel yükleniyor: {args.model} (ilk seferde indirilir, sonrası offline)")
    engine = WhisperEngine(model_size=args.model, compute_type=args.compute_type)

    print("Transkript ediliyor...")
    t0 = time.monotonic()
    result = engine.transcribe(audio_path, language=args.language)
    elapsed = time.monotonic() - t0

    if not result.segments:
        sys.exit("Transkript boş: konuşma algılanamadı.")

    stem = audio_path.stem
    txt_path = write_txt(result, output_dir / f"{stem}.txt")
    srt_path = write_srt(result, output_dir / f"{stem}.srt")

    print(f"\nDil: {result.language} (güven: {result.language_probability:.0%})")
    print(f"Süre: {elapsed:.1f} sn, {len(result.segments)} segment")
    print(f"  → {txt_path}")
    print(f"  → {srt_path}")
    print("\n--- Transkript (ilk 500 karakter) ---")
    print(result.text[:500])


if __name__ == "__main__":
    main()
