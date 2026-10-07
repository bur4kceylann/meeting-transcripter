# CLAUDE.md — Proje Bağlamı

Bu dosya Claude Code tarafından otomatik okunur. Projenin amacını, mimarisini ve
kurallarını burada tanımlıyoruz.

## Proje Amacı

Platformdan bağımsız (Windows, macOS, Linux) çalışan bir CLI aracı.
Bilgisayarın **çıkış sesini** (mikrofon DEĞİL — hoparlörden/sistemden çıkan ses,
yani "loopback") yakalar ve **yerel olarak** (offline, API kullanmadan)
faster-whisper ile metne çevirir.

Sadece transkript çıktısı isteniyor. **Özet / LLM / bulut API YOK.** Maliyet $0.

## Kesin Kurallar (bunlara uy)

- Hiçbir bulut STT veya LLM API'si kullanma. Her şey yerel çalışacak.
- Mikrofon değil, **sistem sesi (loopback)** yakalanacak.
- Platforma özgü kod `src/audio/` altında izole edilecek; ortak kod OS bilmemeli.
- Model dosyaları (`models/`) ve ses kayıtları git'e commit edilmeyecek.
- Türkçe dahil çok dilli transkript desteklenecek (Whisper dili otomatik algılar).

## Hedef Platformlar ve Ses Yakalama Yöntemi

- **Windows** → WASAPI loopback (native, ek sürücü gerekmez). `soundcard` kütüphanesi.
- **macOS** → Core Audio Process Tap (macOS 14.4+, sürücü gerekmez). `tools/audio_tap` (Swift)
  yardımcısı stdout'a PCM yazar, `capture_macos.py` okur.
- **Linux** → PulseAudio / PipeWire "monitor" kaynağı. `sounddevice`.

`src/audio/platform_detect.py` çalışma zamanında OS'u algılayıp doğru modülü seçer.

## Teknoloji Yığını

- Dil: **Python 3.10+**
- STT: **faster-whisper** (CTranslate2 tabanlı, whisper.cpp'nin hızlı Python sürümü)
- Ses: **soundcard** (Windows loopback) + **sounddevice** (Linux) + **tools/audio_tap** (macOS)
- Çıktı: `.txt` ve zaman damgalı `.srt`

## Klasör Yapısı

```
transcript-tool/
├── CLAUDE.md
├── README.md
├── requirements.txt / requirements-dev.txt
├── src/
│   ├── main.py                  # CLI giriş noktası
│   ├── app/                     # OS bilmeyen uygulama çekirdeği
│   │   ├── controller.py        # durum makinesi: kayıt → transkript → dosya
│   │   ├── model_manager.py     # model hazır mı / ilerlemeli indirme
│   │   ├── paths.py             # paketli / kaynak klasörleri
│   │   └── logging_setup.py
│   ├── ui/                      # ince platform kabukları
│   │   ├── menubar_macos.py     # macOS menü çubuğu (rumps)
│   │   ├── macos_system.py      # bildirim, oturum açılışında başlatma
│   │   └── status_text.py       # durum → menü metinleri
│   ├── audio/
│   │   ├── platform_detect.py   # OS algıla, doğru capture modülünü döndür
│   │   ├── capture_windows.py   # WASAPI loopback
│   │   ├── capture_macos.py     # tools/audio_tap'ten PCM okur
│   │   └── capture_linux.py     # PulseAudio monitor
│   ├── transcribe/
│   │   └── whisper_engine.py    # faster-whisper sarmalayıcı
│   └── output/
│       └── writer.py            # .txt / .srt yazma
├── tools/
│   └── audio_tap.swift          # Core Audio Process Tap yardımcısı
├── packaging/                   # PyInstaller spec, imzalama/DMG/notarization betiği
├── models/                      # (gitignore) indirilen Whisper modelleri
└── tests/
```

## Geliştirme Sırası (bu sırayla ilerle)

1. `requirements.txt`, `.gitignore` ve klasör iskeleti.
2. `platform_detect.py` — OS algılama + arayüz sözleşmesi (her capture modülü aynı
   fonksiyon imzasını sağlamalı: örn. `record(callback)` / `stop()`).
3. Önce **geliştiricinin kendi OS'una** ait capture modülünü yaz ve TEST ET.
4. `whisper_engine.py` — yakalanan ses parçalarını faster-whisper'a verip metin döndür.
5. `writer.py` — sonucu .txt ve .srt olarak kaydet.
6. `main.py` — hepsini birleştiren CLI (başlat / durdur / dosyaya yaz).
7. Diğer platformların capture modüllerini sonradan ekle.

## Çalışma Modu Kararı

İlk sürüm **kayıt-sonrası (post-hoc)** transkript üretsin: ses yakalanır, durdurulunca
tek seferde transkript edilir. Gerçek zamanlı (canlı akan) mod v2'ye bırakılabilir.

## Test / Doğrulama

Her modülü yazdıktan sonra küçük bir manuel testle çalıştığını doğrula
(örn. 10 saniye sistem sesi yakala → dosyaya WAV yaz → oynat → doğru mu?).
Bir sonraki modüle geçmeden önce mevcut modülün çalıştığından emin ol.

Birim testleri: `pytest`. Gerçek ses/model gerektirenler: `pytest -m e2e`. Dağıtım: `docs/release.md`.
