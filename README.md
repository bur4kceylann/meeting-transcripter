# transcript-tool

Capture your computer's **system/output audio** (not the microphone — the
loopback signal from meetings, calls, and videos) and transcribe it to text
**fully offline**, with no cloud API and no cost. Point it at a Zoom/Meet/Teams
call, a YouTube video, or any other audio playing on your machine, and get a
clean `.txt` + timestamped `.srt` transcript, powered locally by
[faster-whisper](https://github.com/SYSTRAN/faster-whisper). Works on Windows,
macOS, and Linux.

---

Bilgisayarın çıkış sesini (sistem/hoparlör sesi — mikrofon değil) yakalayıp
**yerel olarak** metne çeviren, platformdan bağımsız bir CLI aracı.
Tactiq benzeri, ama sadece transkript odaklı, offline ve ücretsiz.

## Özellikler

- Windows / macOS / Linux desteği
- Sistem sesini (loopback) yakalama
- faster-whisper ile yerel transkripsiyon (API yok, internet gerektirmez)
- `.txt` ve zaman damgalı `.srt` çıktısı
- Çok dilli (Türkçe dahil, dil otomatik algılanır)

## Gereksinimler

- Python 3.10+
- Platforma göre ses altyapısı:
  - **Windows:** ek kurulum gerekmez (WASAPI loopback)
  - **macOS:** [BlackHole](https://github.com/ExistentialAudio/BlackHole) sanal ses sürücüsü
  - **Linux:** PulseAudio veya PipeWire (çoğu dağıtımda hazır gelir)

## Kurulum

```bash
git clone <repo-url>
cd transcript-tool
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

macOS'ta menü çubuğu uygulaması, ses çıkışını yönlendirmek için küçük bir Swift
yardımcısına ihtiyaç duyar (derlenmiş hali git'e dahil değildir, bir kere
derlemen yeterli):

```bash
swiftc -O tools/audio_route.swift -o tools/audio_route
```

## Kullanım (macOS — menü çubuğu uygulaması)

```bash
bash tools/toggle.sh    # uygulamayı başlatır ve kaydı açar
```

- Menü çubuğundaki **🎙** simgesine tıkla → kayıt başlar (🔴 + süre görünür)
- Tekrar tıkla → kayıt durur, transkript üretilir, bitince `.txt` otomatik açılır
- Kayıt başlarken ses çıkışı otomatik "Hoparlör + BlackHole"a alınır,
  kayıt bitince eski cihaza geri döner
- Klavye kısayolu: macOS **Kısayollar** uygulamasında `tools/toggle.sh`'ı
  çalıştıran bir kısayol oluşturup tuş ata (aşağıda "Klavye Kısayolu")

### Klavye Kısayolu Atama (bir kere)

1. **Kısayollar** (Shortcuts) uygulamasını aç → **+** ile yeni kısayol
2. "Kabuk Betiği Çalıştır" (Run Shell Script) eylemini ekle, içine yaz:
   `bash <proje-yolu>/tools/toggle.sh`
3. Kısayola isim ver (örn. "Transkript"), bilgi panelinden
   **Klavye Kısayolu Ekle** ile bir tuş ata (örn. ⌥⌘R)
4. İlk çalıştırmada Kısayollar betik izni isterse
   Ayarlar → Gelişmiş → "Betiklerin çalıştırılmasına izin ver"i aç

Aynı tuş hem başlatır hem durdurur; uygulama kapalıysa açar ve kaydı başlatır.

## Kullanım (CLI)

```bash
python src/main.py                    # kaydı başlat, Ctrl+C ile durdur
# durunca transkript üretilir ve output/ altına yazılır (.wav + .txt + .srt)

python src/main.py toplanti.wav       # var olan bir ses dosyasını transkript et
python src/main.py --model medium     # daha büyük/doğru model (tiny/base/small/medium/large-v3)
python src/main.py --language tr      # dili elle sabitle (varsayılan: otomatik algıla)
```

## Notlar

- İlk çalıştırmada Whisper modeli otomatik indirilir (`models/` altına).
- macOS'ta sistem sesini yakalamak için ses çıkışını BlackHole'a yönlendirmen gerekir
  (veya Multi-Output Device oluştur ki hem duyabilesin hem kaydedebilesin).

## Lisans

Kişisel kullanım.
