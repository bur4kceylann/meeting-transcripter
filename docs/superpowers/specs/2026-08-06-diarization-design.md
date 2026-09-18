# Konuşmacı Ayırma (Diarization) — Tasarım

Tarih: 2026-08-06

## Amaç

Mevcut transkript aracına, hangi cümleyi hangi konuşmacının söylediğini
belirleyen opsiyonel bir "diarization" adımı eklemek. Toplantı kayıtlarında
`Konuşmacı 1: ...` / `Konuşmacı 2: ...` şeklinde ayrıştırılmış çıktı üretir.

Tamamen **local/offline** çalışır (proje kuralı: bulut API/LLM yok, maliyet $0).
Model indirmesi ücretsiz bir HuggingFace hesabı + token gerektirir (bir kereye
mahsus, sonrası offline).

## Kapsam

- `--diarize` opt-in CLI flag'i (varsayılan kapalı — mevcut hızlı akışı bozmaz).
- `--speakers N` opsiyonel (konuşmacı sayısı biliniyorsa daha isabetli sonuç;
  verilmezse pyannote otomatik tahmin eder).
- TXT ve SRT çıktısına konuşmacı etiketi ekleme.
- Menü çubuğu uygulaması (`menubar_macos.py`) bu spec kapsamı dışında —
  ilk sürüm sadece CLI (`main.py`) üzerinden.

## Yaklaşım

**pyannote.audio 3.1** speaker-diarization pipeline'ı. Ses dosyasını verince
zaman damgalı "speaker turn" listesi (`0:00-0:15 SPEAKER_00`, ...) döndürür.
Bu turn'ler, Whisper'ın ürettiği metin segmentleriyle zaman örtüşmesine göre
eşleştirilir (her Whisper segmentine en çok çakıştığı speaker atanır — basit
"en çok örtüşme" mantığı, ses ayrıştırma/embedding karşılaştırması yok).

Alternatif değerlendirildi: NeMo/SpeechBrain diarization — daha ağır kurulum,
daha az olgun Python API'si. pyannote bu iş için yaygın kullanılan, faster-whisper
ile en sık eşleştirilen seçenek olduğu için tercih edildi.

## Bileşenler

- **`src/diarize/__init__.py`** (yeni paket)
- **`src/diarize/diarizer.py`** (yeni)
  - `SpeakerTurn` dataclass: `start: float`, `end: float`, `speaker: str`
  - `diarize(audio_path: str | Path, num_speakers: int | None = None) -> list[SpeakerTurn]`
  - `HF_TOKEN` ortam değişkeninden okunur. Yoksa/geçersizse net Türkçe hata
    mesajı (HF hesabı + token alma adımlarını tekrar özetleyen).
- **`src/diarize/merge.py`** (yeni)
  - `assign_speakers(segments: list[Segment], turns: list[SpeakerTurn]) -> list[LabeledSegment]`
  - `LabeledSegment`: `Segment`'in speaker etiketli hali (`start, end, text, speaker`).
  - Örtüşme yoksa (0 turn / sessiz kayıt) speaker `None` — writer bunu
    etiketsiz yazar, crash etmez.
  - Ardışık aynı-konuşmacı segmentleri writer seviyesinde birleştirilir
    (okunabilirlik için, her cümleyi ayrı etiketlemek yerine).
- **`src/output/writer.py`** güncelleme
  - `write_txt`/`write_srt` fonksiyonlarına opsiyonel `labeled_segments` parametresi.
  - Verilirse: TXT'de `Konuşmacı 1: ...` formatı (ardışık aynı konuşmacı
    birleştirilmiş); SRT'de her blok başına `[Konuşmacı 1]` etiketi.
  - Verilmezse: mevcut davranış aynen korunur (geriye dönük uyumlu, mevcut
    testler/kullanım bozulmaz).
- **`main.py`** güncelleme
  - `--diarize` (store_true, varsayılan False)
  - `--speakers` (int, opsiyonel)
  - `--diarize` verilmemişse `src/diarize` hiç import edilmez/yüklenmez
    (torch + pyannote yükü olmadan mevcut akış aynı hızda kalır).
- **`requirements.txt`**: `pyannote.audio` eklenir (torch bağımlılığını
  beraberinde getirir; ilk kurulumda büyük indirme, sonrası offline).
- **`.env.example`** (yeni, git'e commit edilir) — `HF_TOKEN=` satırı, açıklama
  yorumuyla. Gerçek `.env` zaten `.gitignore`'da olmalı (kontrol edilecek).

## Veri Akışı

```
WAV → [Whisper transcribe] → Segment listesi (zaman damgalı metin)
WAV → [pyannote diarize]   → SpeakerTurn listesi (zaman damgalı, konuşmacı id)
                ↓
        merge.assign_speakers() — zaman örtüşmesiyle eşleştir
                ↓
        LabeledSegment listesi
                ↓
        writer.write_txt / write_srt → "Konuşmacı 1: ..." etiketli çıktı
```

## Hata Durumları

- `HF_TOKEN` yok/geçersiz → net Türkçe hata + HF hesap/token adımlarının özeti,
  program `--diarize` olmadan da çalışabildiğini hatırlatır.
- Diarization 0 turn dönerse (çok kısa/sessiz kayıt) → tüm metin etiketsiz
  tek blok olarak yazılır (crash yok).
- pyannote model indirme başarısız olursa (ağ sorunu, gated model onayı
  eksik) → hatayı olduğu gibi kullanıcıya göster + ilk kurulum adımlarını
  tekrar hatırlat.

## Test Planı

- `merge.assign_speakers()` için birim testleri: tam örtüşme, kısmi örtüşme,
  örtüşme yok, birden fazla turn'e yayılan segment.
- `writer.py` için: `labeled_segments` verilen/verilmeyen durumda TXT/SRT
  çıktısının doğru formatlandığını doğrulayan testler.
- `diarizer.py` gerçek model indirme gerektirdiği için birim testte
  mock'lanır (pyannote pipeline çağrısı sahte turn listesi döndürecek
  şekilde patch'lenir); gerçek model ile manuel doğrulama kullanıcı
  tarafından `HF_TOKEN` sağlandıktan sonra yapılır.
