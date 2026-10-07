"""PyInstaller giriş noktası (Transkript.app).

`--self-test <model_dir> <ses_dosyası>`: paketin tüm ağır bağımlılıklarının
(ctranslate2, onnxruntime VAD, PyAV) imzalı paket içinde yüklenebildiğini
doğrulamak için transkripti stdout'a yazar ve çıkar. Derleme betiği kullanır.
"""

import multiprocessing
import sys


def _self_test(model_dir: str, audio_path: str) -> None:
    from src.transcribe.whisper_engine import WhisperEngine

    result = WhisperEngine(model_size=model_dir).transcribe(audio_path)
    print(result.text)


if __name__ == "__main__":
    # Paketli uygulamada multiprocessing (ör. resource_tracker) kendi ikilisini alt süreç
    # olarak çalıştırır; freeze_support o çağrıları yakalayıp görevini yapar ve çıkar.
    multiprocessing.freeze_support()
    if len(sys.argv) == 4 and sys.argv[1] == "--self-test":
        _self_test(sys.argv[2], sys.argv[3])
        sys.exit(0)
    from src.ui.menubar_macos import main

    main()
