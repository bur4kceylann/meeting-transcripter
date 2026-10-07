# transcript-tool

Capture your computer's **system/output audio** (not the microphone; the
loopback signal from meetings, calls, and videos) and transcribe it to text
**fully offline**, with no cloud API and no cost. Point it at a Zoom/Meet/Teams
call, a YouTube video, or any other audio playing on your machine, and get a
clean `.txt` + timestamped `.srt` transcript, powered locally by
[faster-whisper](https://github.com/SYSTRAN/faster-whisper). Works on Windows,
macOS, and Linux.

---

Bilgisayarın çıkış sesini (sistem/hoparlör sesi, mikrofon değil) yakalayıp
**yerel olarak** metne çeviren, platformdan bağımsız bir araç.
Tactiq benzeri, ama sadece transkript odaklı, offline ve ücretsiz.

## Kurulum (son kullanıcı, macOS)

1. [Releases](https://github.com/bur4kceylann/meeting-transcripter/releases/latest)
   sayfasından `Transkript-x.y.z.dmg` dosyasını indir.
2. Aç, **Transkript**'i **Applications** klasörüne sürükle.
3. Transkript'i aç. Menü çubuğunda model bir kereliğine indirilir (~1.5 GB).
4. 🎙 → **Kaydı Başlat**. İlk kayıtta "sistem sesi kaydı" iznine **İzin Ver**.

Gereksinim: Apple Silicon Mac, macOS 14.4 veya daha yeni.
Transkriptler `Belgeler/Transkriptler` klasörüne yazılır.

## Özellikler

- Windows / macOS / Linux desteği
- Sistem sesini (loopback) yakalama
- faster-whisper ile yerel transkripsiyon (API yok, model indirildikten sonra internet gerekmez)
- `.txt` ve zaman damgalı `.srt` çıktısı
- Çok dilli (Türkçe dahil, dil otomatik algılanır)

## Gereksinimler (geliştirici)

- Python 3.10+
- Platforma göre ses altyapısı:
  - **Windows:** ek kurulum gerekmez (WASAPI loopback)
  - **macOS:** 14.4+ (Core Audio Process Tap; ek sürücü gerekmez)
  - **Linux:** PulseAudio veya PipeWire (çoğu dağıtımda hazır gelir)

## Geliştirici Kurulumu

```bash
git clone https://github.com/bur4kceylann/meeting-transcripter.git
cd meeting-transcripter
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

macOS'ta sistem sesi, küçük bir Swift yardımcısıyla yakalanır (derlenmiş hali
git'e dahil değildir):

```bash
swiftc -O -target arm64-apple-macos14.4 tools/audio_tap.swift -o tools/audio_tap
```

İlk kayıtta macOS, terminal uygulaman için "sistem sesi kaydı" izni ister.

## Kullanım (macOS menü çubuğu, kaynaktan)

```bash
.venv/bin/python src/ui/menubar_macos.py
```

- Menü çubuğundaki **🎙** → **Kaydı Başlat**: kayıt başlar (🔴 + süre görünür).
- **Kaydı Durdur**: transkript üretilir (⏳ + yüzde), bitince `.txt` otomatik açılır.
- Kaynaktan çalışırken model `models/faster-whisper-medium`, çıktılar `output/`,
  loglar `logs/` altındadır.

## Kullanım (CLI)

```bash
python src/main.py                    # kaydı başlat, Ctrl+C ile durdur
# durunca transkript üretilir ve output/ altına yazılır (.wav + .txt + .srt)

python src/main.py toplanti.wav       # var olan bir ses dosyasını transkript et
python src/main.py --model large-v3   # farklı model (tiny/base/small/medium/large-v3)
python src/main.py --language tr      # dili elle sabitle (varsayılan: otomatik algıla)
```

## Test

```bash
pytest           # birim testleri
pytest -m e2e    # gerçek ses yakalama ve model gerektiren testler (macOS, hoparlörden ses çalar)
```

## Paketleme ve Sürüm

İmzalı ve notarize edilmiş `.dmg` üretimi ve GitHub Release süreci için
[docs/release.md](docs/release.md).

## Lisans

Kişisel kullanım.
