# macOS Dağıtımı: Teknik Olmayan Kullanıcı İçin Kurulabilir Uygulama

Tarih: 2026-10-06
Durum: Tasarım onaylandı, spec incelemede

## Amaç

Teknik bilgisi olmayan bir kullanıcı (müdür / ekip arkadaşı) aracı kendi başına
kurup kullanabilmeli. Akış: GitHub Release linkinden `.dmg` indir → uygulamayı
Uygulamalar'a sürükle → aç → menü çubuğundaki 🎙'a tıkla → kayıt → durdur →
`.txt` açılır. Kullanıcı hiçbir noktada terminal, Python, Homebrew veya ses
sürücüsü ayarı görmez.

Bu spec **sadece macOS** alt projesini kapsar. Windows (sistem tepsisi uygulaması
+ Inno Setup kurulum dosyası) ayrı bir alt proje olarak bunun üstüne eklenecek;
bu yüzden uygulama çekirdeği OS bilmeden yazılır.

## Kısıtlar ve Kararlar

- Offline ve $0 kuralı korunur: bulut STT/LLM yok. İnternet yalnızca ilk
  açılışta model indirmek için gerekir.
- Hedef: Apple Silicon (arm64), macOS 14.4+. Intel ve eski macOS desteklenmez.
- Uygulama Developer ID ("BURAK CEYLAN (4F8TVA268Y)") ile imzalanır ve
  notarize edilir; Gatekeeper uyarısı çıkmaz.
- Model (`medium`, ~1.5 GB) pakete gömülmez, ilk açılışta indirilir.
- Dağıtım: public GitHub repo'nun Release'leri. Güncelleme elle (yeni `.dmg`'yi
  indirip üstüne kurmak). Otomatik güncelleme yok.
- Paketleme: mevcut Python kodu PyInstaller ile gömülü Python'lu `.app` olur.
- Uygulama adı "Transkript", bundle id `com.burakceylan.transkript`.

## Kapsam Dışı (v1)

- Windows ve Linux paketleri (Windows sonraki alt proje).
- Klavye kısayolu: `tools/toggle.sh` ve `.toggle_trigger` mekanizması kaldırılır.
  Kullanıcı simgeye tıklar. Gerekirse v2'de uygulama içi yerleşik kısayol.
- Model seçimi menüsü (sabit `medium`).
- Otomatik güncelleme.
- Konuşmacı ayrımı (diarization) gibi yeni transkript özellikleri.

## Mimari

```
src/
├── __init__.py                # __version__ (tek kaynak)
├── main.py                    # CLI, aynen kalır (paths modülünü kullanacak şekilde güncellenir)
├── app/                       # YENİ: OS bilmeyen uygulama çekirdeği
│   ├── __init__.py
│   ├── controller.py          # durum makinesi + kayıt/transkript/yazma akışı
│   ├── model_manager.py       # model var mı, yoksa ilerlemeli indir
│   └── paths.py               # model/çıktı/log klasörleri
├── ui/                        # YENİ: ince platform kabukları
│   ├── __init__.py
│   └── menubar_macos.py       # rumps; src/menubar_macos.py buraya taşınır, iş mantığı controller'a çıkar
├── audio/
│   ├── platform_detect.py     # aynen
│   ├── capture_macos.py       # DEĞİŞİR: BlackHole yerine audio_tap'ten PCM okur
│   ├── capture_windows.py     # aynen
│   └── capture_linux.py       # aynen
├── transcribe/whisper_engine.py  # ilerleme callback'i + models dizini parametresi eklenir
└── output/writer.py           # aynen
tools/
└── audio_tap.swift            # YENİ: Core Audio Process Tap yardımcısı
packaging/
├── transkript.spec            # PyInstaller spec
├── Info.plist ekleri / entitlements.plist
└── build_macos.sh             # derle + imzala + dmg + notarize (yerelde ve CI'da aynı)
.github/workflows/
├── test.yml                   # push/PR'da pytest (macOS)
└── release.yml                # v* etiketinde derle + Release'e yükle
```

Kaldırılanlar: `tools/audio_route.swift`, `tools/audio_route` (derlenmiş),
`tools/toggle.sh`, `.toggle_trigger`, BlackHole'a bağlı kod ve dokümantasyon.
`CLAUDE.md`, `AGENTS.md` ve `README.md` yeni macOS yöntemine göre güncellenir.

### Birimler

**`src/app/paths.py`**
Uygulamanın paketli (`sys.frozen`) mi yoksa kaynaktan mı çalıştığına göre
klasörleri döndürür:

| | Paketli | Kaynaktan |
|---|---|---|
| Modeller | `~/Library/Application Support/Transkript/models` | `<proje>/models` |
| Transkriptler | `~/Documents/Transkriptler` | `<proje>/output` |
| Loglar | `~/Library/Logs/Transkript` | `<proje>/logs` (gitignore) |

Windows karşılıkları (`%LOCALAPPDATA%\Transkript\...`, `Documents\Transkriptler`)
aynı modülde tanımlanır ama bu alt projede test edilmez. Klasörler ilk erişimde
oluşturulur.

**`src/app/model_manager.py`**
- `is_ready() -> bool`: model dosyaları tam olarak mevcut mu.
- `download(on_progress: Callable[[float], None]) -> None`: Hugging Face'ten
  (`Systran/faster-whisper-medium`) dosyaları indirir, toplam bayt üzerinden
  0.0-1.0 ilerleme bildirir. Önce geçici bir klasöre indirir, tamamlanınca
  atomik olarak yerine taşır; hata/kesintide geçici klasör silinir. Bu sayede
  yarım model asla "hazır" görünmez.
- Hata türleri: `ModelDownloadError` (ağ), `DiskFullError` (yer yok). Kabuk
  bunları kullanıcı mesajına çevirir.

**`src/app/controller.py`**
OS ve arayüz bilmeyen durum makinesi. Kabuk, controller'ı çağırır ve
controller'ın yayınladığı durum değişikliklerini gösterir.

Durumlar: `NEEDS_MODEL` → `DOWNLOADING(progress)` → `IDLE` ⇄ `RECORDING(elapsed)`
→ `TRANSCRIBING(progress)` → `IDLE`. Ek olarak `ERROR(kind)` (indirme hatası →
"Tekrar Dene" ile `DOWNLOADING`'e döner).

Arayüzü:
- `start()`: model hazırsa `IDLE`, değilse indirmeyi başlatır.
- `toggle()`: `IDLE`'da kaydı başlatır, `RECORDING`'de durdurup transkripti arka
  planda başlatır; `DOWNLOADING`/`TRANSCRIBING`'de bilgi mesajı yayınlar.
- `retry_download()`, `shutdown()`.
- Olaylar (callback): `on_state(state)`, `on_message(title, body)`,
  `on_transcript_ready(txt_path)`.

Bağımlılıklar yapıcıdan verilir (capture factory, engine factory, model
manager, writer, paths); testlerde sahteleri verilir. Ağır işler (indirme,
transkript) worker thread'de çalışır; kabuk callback'leri kendi ana thread'ine
aktarmaktan sorumludur (rumps'ta mevcut `Timer` ile kuyruk boşaltma deseni).

Transkript ilerlemesi: faster-whisper segmentleri sırayla üretir;
`segment.end / audio_duration` oranı yüzde olarak yayınlanır.

Sessiz kayıt: kaydedilen sesin RMS'i eşik altındaysa transkript yine üretilir,
ek olarak "Kayıtta ses algılanmadı" mesajı yayınlanır.

**`src/transcribe/whisper_engine.py`**
`models_dir` parametresi (varsayılan `paths`'ten) ve
`transcribe(..., on_progress=None)` eklenir. Var olan CLI davranışı değişmez.

**`tools/audio_tap.swift` + `src/audio/capture_macos.py`**
- `audio_tap` (komut satırı yardımcısı): `CATapDescription` ile tüm süreçlerin
  çıkışını kapsayan global bir process tap (kendi süreci hariç) ve buna bağlı
  özel (private) bir aggregate device oluşturur. IOProc ile gelen ses stdout'a
  ham float32 interleaved PCM olarak yazılır. Başlangıçta stderr'e tek satır
  JSON yazar: `{"samplerate": 48000, "channels": 2}`. SIGTERM / stdin
  kapanınca tap ve aggregate device'ı temizleyip çıkar. İzin reddedilirse
  ayırt edilebilir bir çıkış koduyla (ör. 77) çıkar.
- `MacOSCapture` mevcut sözleşmeyi (`start/stop/device_hint/samplerate/channels`)
  korur: `start()` yardımcıyı alt süreç olarak başlatır ve bir thread'de
  stdout'u okur, `stop()` süreci sonlandırıp float32 mono ses döndürür.
  Yardımcının yolu paketli uygulamada `.app` içinden, kaynaktan çalışırken
  `tools/audio_tap`'ten çözülür.
- Kullanıcının ses çıkışı hiç değişmez; ses tuşları, AirPods vb. normal çalışır.
- İzin: `Info.plist`'e `NSAudioCaptureUsageDescription` ("Toplantı ve
  videolardaki sesi metne çevirmek için sistem sesini kaydeder.") eklenir.
  Yardımcı `.app`'in alt süreci olduğu için TCC izni uygulamaya atfedilir.
  İlk kayıtta macOS izin penceresini gösterir.

**`src/ui/menubar_macos.py`**
Sadece gösterim: controller durumunu simge/başlığa, mesajları bildirime çevirir.

| Durum | Menü çubuğu |
|---|---|
| `DOWNLOADING` | `⬇️ %42` |
| `IDLE` | `🎙` |
| `RECORDING` | `🔴 03:12` |
| `TRANSCRIBING` | `⏳ %35` |
| `ERROR` | `⚠️` |

Menü: Kaydı Başlat/Durdur · Son Transkripti Aç · Transkript Klasörünü Aç ·
Oturum açıldığında başlat ✓ · (duruma göre) Tekrar Dene / İzni Aç… /
Hata Kaydını Göster · Hakkında (sürüm) · Çıkış.

- "Oturum açıldığında başlat": `SMAppService.mainApp` (pyobjc ile). İlk
  açılışta varsayılan olarak etkinleştirilir; menüden kapatılabilir.
- "İzni Aç…": `x-apple.systempreferences:com.apple.preference.security?Privacy_AudioCapture`
  sayfasını açar.
- Transkript sırasında Çıkış: onay penceresi; ses dosyası korunur.
- Uygulama Dock'ta görünmez (`LSUIElement`).

## Kullanıcı Akışı

İlk kurulum:
1. `.dmg` → Transkript'i Uygulamalar'a sürükle → aç (Gatekeeper uyarısı yok).
2. Menü çubuğunda `⬇️ %0` → indirme biter → "Hazır, 🎙'a tıklayıp kayda
   başlayabilirsin" bildirimi.
3. İlk kayıtta sistem sesi izin penceresi → "İzin Ver".

Günlük: 🎙 → Kaydı Başlat → `🔴 süre` → Kaydı Durdur → `⏳ %` → bildirim +
`.txt` varsayılan editörde açılır. Çıktılar (`.wav`, `.txt`, `.srt`)
`~/Documents/Transkriptler`'e yazılır.

## Hata Durumları

| Durum | Davranış |
|---|---|
| İndirme sırasında ağ koptu / disk doldu | Bildirim ("Model indirilemedi, internetini kontrol et" / "Diskte yeterli yer yok"), `⚠️`, menüde "Tekrar Dene"; yarım indirme silinir |
| İndirme bitmeden kayıt istendi | "Model hazırlanıyor (%42), bitince kayıt yapabilirsin." |
| Sistem sesi izni reddedildi | "Sistem sesine izin verilmedi" bildirimi + "İzni Aç…" menüsü |
| Sessiz kayıt | Transkript üretilir + "Kayıtta ses algılanmadı" uyarısı |
| Transkript sırasında çıkış | Onay sorulur, ses dosyası korunur |
| Beklenmedik hata | "Bir sorun oluştu" bildirimi; tam traceback loga yazılır; "Hata Kaydını Göster" menüsü log klasörünü açar |

Loglama: standart `logging`, dönen dosya (`RotatingFileHandler`, 1 MB × 3).

## Derleme, İmzalama, Dağıtım

**`packaging/build_macos.sh`** (yerelde ve CI'da aynı betik):
1. `swiftc -O tools/audio_tap.swift` → `audio_tap`.
2. PyInstaller (`packaging/transkript.spec`, onedir, `BUNDLE`) → `Transkript.app`;
   `audio_tap` `Contents/MacOS/` (veya `Contents/Resources/bin`) altına konur;
   `Info.plist`'e sürüm, `LSUIElement`, `NSAudioCaptureUsageDescription`,
   `LSMinimumSystemVersion=14.4` eklenir.
3. İmzalama: içten dışa her Mach-O (`.dylib`, `.so`, yardımcı ikili) `codesign
   --options runtime --timestamp --sign "Developer ID Application: ..."`; en son
   `.app`. Entitlement'lar en dar haliyle (ctranslate2/PyInstaller ihtiyacına
   göre uygulama sırasında belirlenir).
4. `.dmg` (Uygulamalar kısayolu ile) oluştur ve imzala.
5. `xcrun notarytool submit --wait`, ardından `xcrun stapler staple`.
6. Doğrulama: `spctl -a -vv -t install`, `stapler validate`.

Kimlik bilgileri ortam değişkenlerinden okunur (yerelde keychain profili,
CI'da secrets). Çıktı: `dist/Transkript-<sürüm>.dmg`.

**GitHub Actions**
- `test.yml`: push/PR'da `macos-14` üzerinde `pytest`.
- `release.yml`: `v*` etiketinde `macos-14` üzerinde testler + `build_macos.sh`;
  `.dmg`'yi GitHub Release'e yükler. Release açıklamasına kullanıcı için
  Türkçe kurulum talimatı (`packaging/release-notes.md` şablonundan) eklenir.
- Gerekli secrets (kullanıcı bir kere ekler, adımlar ayrıca anlatılacak):
  Developer ID sertifikası (`.p12` base64 + parola), App Store Connect API
  anahtarı (key id, issuer id, `.p8`).

## Test

- **Birim (pytest, sahte bağımlılıklarla):**
  - controller durum geçişleri: normal akış, indirme sırasında toggle,
    transkript sırasında toggle, sessiz kayıt, indirme hatası → Tekrar Dene,
    kapatma.
  - transkript ilerleme yüzdesi hesabı.
  - model_manager: başarılı indirme, kesinti (geçici klasör silinir, `is_ready`
    false kalır), disk dolu.
  - paths: paketli / kaynaktan ayrımı.
- **audio_tap E2E (geliştirici Mac'i, otomatik test):** kayıt sürerken `say`
  ile bilinen Türkçe cümle çalınır; transkriptte anahtar kelimelerin geçtiği
  doğrulanır. Ses çıkış cihazının değişmediği de kontrol edilir.
- **Paketli uygulama E2E (elle):** notarize `.dmg`, mümkünse Mac'te yeni ve boş
  bir kullanıcı hesabında kurulur: `spctl` kabul, ilk açılış indirme ilerlemesi,
  izin penceresi, YouTube videosu transkripti, Oturum açıldığında başlat,
  hata yolları (indirme sırasında Wi-Fi kapatma, izni reddetme). Menü, simge
  ve bildirim metinleri piksel düzeyinde gözden geçirilir.

## Açık Riskler

- PyInstaller + ctranslate2 paketinin notarization'dan geçmesi için gereken
  entitlement'lar deneme ile netleşecek.
- Process Tap izninin alt süreçteki yardımcıya değil `.app`'e atfedilmesi
  beklenen davranış; paketli E2E'de doğrulanacak. Atfedilmezse tap kodu
  Python sürecine (pyobjc) veya yardımcı `.app` içine taşınır.
- Hugging Face erişimi şirket ağında engelliyse indirme başarısız olur; hata
  mesajı bunu kapsar, ileride alternatif indirme kaynağı (GitHub Release asset)
  eklenebilir.
