# macOS Dağıtımı Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teknik olmayan bir kullanıcının GitHub Release'ten indirip çift tıklayarak kurabileceği, imzalı ve notarize edilmiş bir `Transkript.dmg` üretmek.

**Architecture:** Mevcut Python çekirdeği (yakalama, faster-whisper, writer) korunur. Üstüne OS bilmeyen bir uygulama çekirdeği (`src/app/`: durum makinesi, model indirici, klasörler) ve ince bir rumps menü çubuğu kabuğu (`src/ui/`) eklenir. macOS ses yakalama BlackHole yerine Core Audio Process Tap kullanan küçük bir Swift yardımcısıyla (`tools/audio_tap`) yapılır. PyInstaller `.app` üretir, `packaging/build_macos.sh` imzalar, `.dmg`'ye koyar ve notarize eder; GitHub Actions bunu `v*` etiketinde çalıştırıp Release'e yükler.

**Tech Stack:** Python 3.13, faster-whisper 1.2, httpx, rumps, pyobjc (ServiceManagement, UserNotifications), Swift (CoreAudio / AudioToolbox), PyInstaller 6, pytest, GitHub Actions (`macos-15`).

**Spec:** `docs/superpowers/specs/2026-10-06-macos-distribution-design.md`

## Global Constraints

- Bulut STT/LLM yok; internet yalnızca ilk açılışta model indirmek için.
- Hedef: Apple Silicon (arm64), `LSMinimumSystemVersion` = `14.4`.
- Uygulama adı `Transkript`, bundle id `com.burakceylan.transkript`.
- İmza kimliği: `Developer ID Application: BURAK CEYLAN (4F8TVA268Y)`.
- Model: `Systran/faster-whisper-medium`, ilk açılışta indirilir, pakete gömülmez.
- Paketli uygulamada klasörler: modeller `~/Library/Application Support/Transkript/models`, transkriptler `~/Documents/Transkriptler`, loglar `~/Library/Logs/Transkript`.
- Kaynaktan çalışırken: `<proje>/models`, `<proje>/output`, `<proje>/logs`.
- Platforma özgü ses kodu `src/audio/` altında kalır; `src/app/` OS bilmez.
- Kullanıcıya görünen tüm metinler Türkçe ve teknik ayrıntısız; ayrıntı log dosyasına.
- Metinlerde ve kodda em dash ("—") kullanılmaz, düz tire ("-") kullanılır.
- Commit mesajlarına ajan adı / co-author satırı eklenmez.
- Model dosyaları, ses kayıtları, `build/`, `dist/`, derlenmiş `tools/audio_tap` git'e girmez.

## Review Focus

1. **Uzun kayıt (1 saat ve üzeri):** yakalama tüm sesi kayıpsız biriktirmeli, bellek stereo yerine mono tutulmalı. Task 2'de 10 saniyelik 48 kHz stereo veriyi küçük parçalar halinde yazan sahte yardımcıyla örnek sayısı birebir doğrulanır.
2. **Kayıt sırasında ses çıkışı değişir veya yardımcı ölür** (AirPods takılır/çıkar, audio_tap çöker): o ana kadar yakalanan ses kaybolmamalı, `stop()` hata fırlatmamalı. Task 2'de "yardımcı erken EOF verir" testi; Task 11'de AirPods ile elle kontrol.
3. **Yarıda kalan veya eksik model indirmesi:** model asla "hazır" görünmemeli, `.partial` klasörü kalmamalı. Task 4'te ağ hatası, eksik bayt (truncated) ve ENOSPC testleri.
4. **Uygulama çökünce yetim yardımcı:** üst süreç ölünce `audio_tap` stdin kapanışını görüp kendini temizlemeli. Task 1'de `kill -9` ile elle doğrulanır.
5. **Bildirim metninde Türkçe karakter / tırnak / dosya adı:** AppleScript bildirim komutu kırılmamalı. Task 7'de komut oluşturucunun testi.

---

## Dosya Haritası

| Dosya | Sorumluluk |
|---|---|
| `requirements.txt`, `requirements-dev.txt`, `pytest.ini` | Bağımlılıklar, test ayarları (Task 0) |
| `src/__init__.py` | `__version__` tek kaynak (Task 0) |
| `tools/audio_tap.swift` | Process Tap ile sistem sesini stdout'a yazar (Task 1) |
| `src/audio/platform_detect.py` | `CapturePermissionError` eklenir (Task 2) |
| `src/audio/capture_macos.py` | audio_tap alt sürecinden PCM okur (Task 2) |
| `src/app/paths.py` | Paketli/kaynak klasörleri (Task 3) |
| `src/app/logging_setup.py` | Dönen log dosyası + yakalanmamış hata kaydı (Task 3) |
| `src/app/model_manager.py` | Model hazır mı / ilerlemeli atomik indirme (Task 4) |
| `src/transcribe/whisper_engine.py` | `on_progress` callback'i (Task 5) |
| `src/app/controller.py` | OS bilmeyen durum makinesi (Task 6) |
| `src/ui/status_text.py` | Durum → menü çubuğu başlığı/etiketleri (saf fonksiyonlar) (Task 7) |
| `src/ui/macos_system.py` | Bildirim, dosya açma, oturum açılışında başlatma (Task 7) |
| `src/ui/menubar_macos.py` | rumps kabuğu (Task 7) |
| `src/main.py`, `README.md`, `CLAUDE.md`, `AGENTS.md` | CLI ve dokümantasyon güncellemesi (Task 8) |
| `packaging/*` | İkon, PyInstaller spec, entitlements, giriş noktası, derleme betiği (Task 9) |
| `.github/workflows/*`, `packaging/release-notes.md`, `docs/release.md` | CI ve sürüm süreci (Task 10) |

Silinecekler (Task 7): `src/menubar_macos.py`, `tools/audio_route.swift`, `tools/toggle.sh`, derlenmiş `tools/audio_route`, `.toggle_trigger`.

---

### Task 0: Geliştirme ortamı, sürüm numarası, bağımlılık temizliği

**Files:**
- Modify: `requirements.txt`
- Create: `requirements-dev.txt`, `pytest.ini`
- Modify: `src/__init__.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `src.__version__: str` (= `"0.1.0"`); `pytest` komutu proje kökünden `src.` importlarıyla çalışır; `@pytest.mark.e2e` işaretli testler varsayılan olarak atlanır, `pytest -m e2e` ile çalışır.

- [ ] **Step 1: `requirements.txt`'i yeniden yaz**

```
# Yerel konuşma-metin (offline, CTranslate2 tabanlı)
faster-whisper>=1.1.0

# Model indirme (ilk açılışta, ilerleme göstererek)
httpx>=0.27

# Ses yakalama
# macOS: tools/audio_tap (Core Audio Process Tap), ek Python paketi gerekmez
sounddevice>=0.4.6 ; sys_platform == "linux"     # PulseAudio / PipeWire monitor
soundcard>=0.4.3 ; sys_platform == "win32"       # WASAPI loopback

# Ses verisi işleme / WAV yazma
numpy>=1.24
soundfile>=0.12.1

# macOS menü çubuğu uygulaması
rumps>=0.4.0 ; sys_platform == "darwin"
pyobjc-framework-ServiceManagement>=10 ; sys_platform == "darwin"
pyobjc-framework-UserNotifications>=10 ; sys_platform == "darwin"
```

- [ ] **Step 2: `requirements-dev.txt` oluştur**

```
-r requirements.txt
pytest>=8
pyinstaller>=6.10
```

- [ ] **Step 3: `pytest.ini` oluştur**

```ini
[pytest]
testpaths = tests
pythonpath = .
markers =
    e2e: gerçek ses donanımı / model gerektiren testler (pytest -m e2e ile çalıştır)
addopts = -m "not e2e"
```

- [ ] **Step 4: `src/__init__.py` içeriği**

```python
__version__ = "0.1.0"
```

- [ ] **Step 5: `.gitignore` güncelle.** `# Derlenen yardımcılar ve çalışma zamanı dosyaları` bloğunu şununla değiştir:

```
# Derlenen yardımcılar, paketleme ve çalışma zamanı dosyaları
tools/audio_tap
/build/
/dist/
/logs/
/.state/
```

- [ ] **Step 6: Bağımlılıkları kur ve mevcut testleri çalıştır**

Run: `.venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q`
Expected: `tests/test_writer.py` testleri PASS (unittest testleri pytest altında da çalışır).

- [ ] **Step 7: Commit**

```bash
git add requirements.txt requirements-dev.txt pytest.ini src/__init__.py .gitignore
git commit -m "chore: pytest, sürüm numarası ve platforma göre bağımlılıklar"
```

---

### Task 1: `audio_tap` Swift yardımcısı (Core Audio Process Tap)

**Files:**
- Create: `tools/audio_tap.swift`

**Interfaces:**
- Produces: `tools/audio_tap` komut satırı aracı. Sözleşme:
  - stderr ilk satır: `{"samplerate": <int>, "channels": <int>}\n`
  - stdout: float32 little-endian interleaved PCM
  - SIGTERM / SIGINT / stdin EOF → kaynakları temizleyip `exit(0)`
  - Tap oluşturulamazsa `exit(77)`, diğer hatalar `exit(1)`; hata mesajı stderr'e `audio_tap: ...` ile başlar.

- [ ] **Step 1: `tools/audio_tap.swift` yaz**

```swift
// audio_tap: macOS sistem sesini (tüm süreçlerin çıkışı) Core Audio Process Tap
// ile yakalar ve stdout'a ham float32 interleaved PCM olarak yazar.
// Kullanıcının ses çıkışı değişmez; ses duyulmaya devam eder.
//
// Protokol:
//   stderr ilk satır: {"samplerate": 48000, "channels": 2}
//   stdout: float32 little-endian interleaved örnekler
//   SIGTERM / SIGINT ya da stdin kapanınca (üst süreç öldü) temizleyip çıkar.
//   Çıkış kodları: 0 normal, 77 tap oluşturulamadı (izin), 1 diğer hatalar.
//
// macOS 14.4+ gerekir. Derleme:
//   swiftc -O -target arm64-apple-macos14.4 tools/audio_tap.swift -o tools/audio_tap

import AudioToolbox
import CoreAudio
import Foundation

setvbuf(stdout, nil, _IOFBF, 1 << 16)

func fail(_ message: String, code: Int32) -> Never {
    FileHandle.standardError.write("audio_tap: \(message)\n".data(using: .utf8)!)
    exit(code)
}

func getProperty<T>(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector, _ value: inout T) -> OSStatus {
    var address = AudioObjectPropertyAddress(
        mSelector: selector,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    var size = UInt32(MemoryLayout<T>.size)
    return AudioObjectGetPropertyData(object, &address, 0, nil, &size, &value)
}

// 1) Varsayılan çıkış cihazı: aggregate cihazın saat kaynağı olur
var outputID = AudioObjectID(kAudioObjectUnknown)
guard getProperty(AudioObjectID(kAudioObjectSystemObject), kAudioHardwarePropertyDefaultOutputDevice, &outputID) == noErr else {
    fail("varsayılan çıkış cihazı bulunamadı", code: 1)
}
var outputUIDRef: Unmanaged<CFString>?
guard getProperty(outputID, kAudioDevicePropertyDeviceUID, &outputUIDRef) == noErr, let outputUIDValue = outputUIDRef else {
    fail("çıkış cihazının UID'si okunamadı", code: 1)
}
let outputUID = outputUIDValue.takeRetainedValue() as String

// 2) Global tap: tüm süreçlerin stereo karışımı, ses susturulmaz
let tapDescription = CATapDescription(stereoGlobalTapButExcludeProcesses: [])
tapDescription.uuid = UUID()
tapDescription.isPrivate = true
tapDescription.muteBehavior = .unmuted
var tapID = AudioObjectID(kAudioObjectUnknown)
let tapStatus = AudioHardwareCreateProcessTap(tapDescription, &tapID)
guard tapStatus == noErr else {
    fail("process tap oluşturulamadı (OSStatus \(tapStatus))", code: 77)
}

var format = AudioStreamBasicDescription()
guard getProperty(tapID, kAudioTapPropertyFormat, &format) == noErr else {
    AudioHardwareDestroyProcessTap(tapID)
    fail("tap ses formatı okunamadı", code: 1)
}

// 3) Tap'i içeren özel (private) aggregate cihaz
let aggregateDescription: [String: Any] = [
    kAudioAggregateDeviceNameKey: "Transkript Tap",
    kAudioAggregateDeviceUIDKey: UUID().uuidString,
    kAudioAggregateDeviceMainSubDeviceKey: outputUID,
    kAudioAggregateDeviceIsPrivateKey: true,
    kAudioAggregateDeviceIsStackedKey: false,
    kAudioAggregateDeviceTapAutoStartKey: true,
    kAudioAggregateDeviceSubDeviceListKey: [[kAudioSubDeviceUIDKey: outputUID]],
    kAudioAggregateDeviceTapListKey: [[
        kAudioSubTapDriftCompensationKey: true,
        kAudioSubTapUIDKey: tapDescription.uuid.uuidString,
    ]],
]
var aggregateID = AudioObjectID(kAudioObjectUnknown)
let aggregateStatus = AudioHardwareCreateAggregateDevice(aggregateDescription as CFDictionary, &aggregateID)
guard aggregateStatus == noErr else {
    AudioHardwareDestroyProcessTap(tapID)
    fail("aggregate cihaz oluşturulamadı (OSStatus \(aggregateStatus))", code: 1)
}

// 4) IOProc: gelen sesi stdout'a yaz (non-interleaved gelirse birleştir)
let channels = Int(format.mChannelsPerFrame)
let isInterleaved = (format.mFormatFlags & kAudioFormatFlagIsNonInterleaved) == 0
let ioQueue = DispatchQueue(label: "audio_tap.io", qos: .userInteractive)
var procID: AudioDeviceIOProcID?
let ioStatus = AudioDeviceCreateIOProcIDWithBlock(&procID, aggregateID, ioQueue) { _, inInputData, _, _, _ in
    let buffers = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: inInputData))
    if isInterleaved || buffers.count == 1 {
        for buffer in buffers {
            if let data = buffer.mData {
                fwrite(data, 1, Int(buffer.mDataByteSize), stdout)
            }
        }
    } else {
        let frames = Int(buffers[0].mDataByteSize) / MemoryLayout<Float>.size
        var interleaved = [Float](repeating: 0, count: frames * buffers.count)
        for (channel, buffer) in buffers.enumerated() {
            guard let samples = buffer.mData?.assumingMemoryBound(to: Float.self) else { continue }
            for frame in 0..<frames {
                interleaved[frame * buffers.count + channel] = samples[frame]
            }
        }
        interleaved.withUnsafeBytes { _ = fwrite($0.baseAddress, 1, $0.count, stdout) }
    }
}
guard ioStatus == noErr, let ioProc = procID else {
    AudioHardwareDestroyAggregateDevice(aggregateID)
    AudioHardwareDestroyProcessTap(tapID)
    fail("IOProc oluşturulamadı (OSStatus \(ioStatus))", code: 1)
}

func cleanup() {
    AudioDeviceStop(aggregateID, ioProc)
    AudioDeviceDestroyIOProcID(aggregateID, ioProc)
    AudioHardwareDestroyAggregateDevice(aggregateID)
    AudioHardwareDestroyProcessTap(tapID)
    fflush(stdout)
}

let header = "{\"samplerate\": \(Int(format.mSampleRate)), \"channels\": \(channels)}\n"
FileHandle.standardError.write(header.data(using: .utf8)!)

let startStatus = AudioDeviceStart(aggregateID, ioProc)
guard startStatus == noErr else {
    cleanup()
    fail("kayıt başlatılamadı (OSStatus \(startStatus))", code: 1)
}

// 5) Durdurma sinyalleri ve üst süreç ölümü (stdin EOF)
signal(SIGTERM, SIG_IGN)
signal(SIGINT, SIG_IGN)
let signalSources = [SIGTERM, SIGINT].map { sig -> DispatchSourceSignal in
    let source = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    source.setEventHandler { cleanup(); exit(0) }
    source.resume()
    return source
}
DispatchQueue.global().async {
    while !FileHandle.standardInput.availableData.isEmpty {}
    DispatchQueue.main.async { cleanup(); exit(0) }
}

withExtendedLifetime(signalSources) { dispatchMain() }
```

- [ ] **Step 2: Derle**

Run: `swiftc -O -target arm64-apple-macos14.4 tools/audio_tap.swift -o tools/audio_tap`
Expected: hata yok (uyarılar kabul). Derleme hatası olursa API imzalarını Xcode'daki `CoreAudio/AudioHardware.h` ve `CATapDescription.h` başlıklarına göre düzelt; sözleşmeyi değiştirme.

- [ ] **Step 3: Elle yakalama testi (Türkçe cümle)**

Run (terminalde, sesin açık olduğundan emin ol):
```bash
D=$(mktemp -d)
./tools/audio_tap > "$D/tap.raw" 2> "$D/tap.err" < /dev/zero &
TAP=$!; sleep 1
say -v Yelda "Bugün toplantıda bütçeyi konuştuk"
sleep 1; kill -TERM $TAP; wait $TAP; echo "çıkış kodu: $?"
head -1 "$D/tap.err"
.venv/bin/python - "$D" <<'EOF'
import json, sys, numpy as np, soundfile as sf
d = sys.argv[1]
fmt = json.loads(open(f"{d}/tap.err").readline())
a = np.fromfile(f"{d}/tap.raw", dtype="<f4").reshape(-1, fmt["channels"]).mean(axis=1)
print("süre:", round(a.size / fmt["samplerate"], 2), "sn, tepe:", round(float(abs(a).max()), 3))
sf.write(f"{d}/tap.wav", a, fmt["samplerate"])
print(f"{d}/tap.wav")
EOF
```
Not: `< /dev/zero` stdin'i hiç EOF vermeyen bir kaynağa bağlar; stdin terminal olsaydı da çalışırdı.
Expected: ilk çalıştırmada macOS terminal uygulaman için "sistem sesi kaydı" izni sorar; izin ver ve komutu tekrar çalıştır. Çıkış kodu `0`, header `{"samplerate": 48000, "channels": 2}` (ya da cihazın hızı), süre yaklaşık 4-5 sn, tepe > 0.05. `afplay <wav yolu>` ile dinle: cümle net duyulmalı. Kayıt sırasında hoparlörden ses normal çıkmalı.

- [ ] **Step 4: Yetim yardımcı kontrolü (Review Focus 4)**

Run:
```bash
.venv/bin/python -c "
import subprocess, time, os
p = subprocess.Popen(['./tools/audio_tap'], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(p.pid); time.sleep(1); os._exit(1)
"
sleep 1; pgrep -fl tools/audio_tap || echo "yardımcı temizlendi"
```
Expected: `yardımcı temizlendi`. Python süreci öldüğünde stdin kapanır ve audio_tap çıkar.

- [ ] **Step 5: Reddedilmiş izin davranışını not et**

Run: `tccutil reset AudioCapture` (terminal uygulamanın iznini sıfırlar), Step 3'ü tekrar çalıştır ve izin penceresinde "İzin Verme"yi seç.
Expected: İki olasılıktan biri; hangisi olduğunu commit mesajına ve `tools/audio_tap.swift` başındaki yorum bloğuna yaz:
  (a) `audio_tap` 77 ile çıkar, ya da
  (b) çalışır ama yalnızca sıfır (sessizlik) üretir.
Controller her iki durumu da karşılar (77 → izin mesajı; sessizlik → "ses algılanmadı + izin ipucu" mesajı). Sonra Ayarlar > Gizlilik ve Güvenlik > Sistem Sesi Kaydı'ndan izni geri aç.

- [ ] **Step 6: Commit**

```bash
git add tools/audio_tap.swift
git commit -m "feat(macos): Core Audio Process Tap ile sürücüsüz sistem sesi yakalayan audio_tap"
```

---

### Task 2: `MacOSCapture` audio_tap'ten okusun

**Files:**
- Modify: `src/audio/platform_detect.py`
- Modify (tamamen yeniden yaz): `src/audio/capture_macos.py`
- Test: `tests/test_capture_macos.py`

**Interfaces:**
- Consumes: Task 1'deki audio_tap protokolü.
- Produces:
  - `src.audio.platform_detect.CapturePermissionError(RuntimeError)`
  - `src.audio.capture_macos.MacOSCapture(helper: str | Path | None = None)`; sözleşme aynı: `samplerate: int`, `channels: int`, `start() -> None`, `stop() -> np.ndarray` (float32 mono), `device_hint() -> str`. `start()` izin yoksa `CapturePermissionError`, yardımcı yoksa `FileNotFoundError`, diğer başlatma hatalarında `RuntimeError` fırlatır. `samplerate` `start()` sonrası yardımcının bildirdiği değerdir.

- [ ] **Step 1: `CapturePermissionError`'ı ekle.** `src/audio/platform_detect.py` içinde `UnsupportedPlatformError` sınıfının altına:

```python
class CapturePermissionError(RuntimeError):
    """İşletim sistemi sistem sesi yakalama iznini vermedi."""
```

- [ ] **Step 2: Başarısız testleri yaz** (`tests/test_capture_macos.py`)

```python
"""MacOSCapture birim testleri: gerçek audio_tap yerine aynı protokolü konuşan sahte yardımcı."""

from __future__ import annotations

import stat
import sys
import textwrap
import time

import numpy as np
import pytest

from src.audio.capture_macos import MacOSCapture
from src.audio.platform_detect import CapturePermissionError


def _fake_helper(tmp_path, body: str):
    script = tmp_path / "fake_tap"
    script.write_text(
        f"#!{sys.executable}\n"
        + textwrap.dedent(
            """
            import signal, struct, sys, time
            signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
            out = sys.stdout.buffer
            def header(rate, ch):
                sys.stderr.write('{"samplerate": %d, "channels": %d}\\n' % (rate, ch))
                sys.stderr.flush()
            """
        )
        + textwrap.dedent(body)
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _record(capture: MacOSCapture, seconds: float = 0.3) -> np.ndarray:
    capture.start()
    time.sleep(seconds)
    return capture.stop()


def test_reads_header_and_downmixes_to_mono(tmp_path):
    helper = _fake_helper(
        tmp_path,
        """
        header(16000, 2)
        out.write(struct.pack('<ff', 0.5, -0.1) * 1000); out.flush()
        while True: time.sleep(0.05)
        """,
    )
    capture = MacOSCapture(helper=helper)
    audio = _record(capture)
    assert capture.samplerate == 16000
    assert capture.channels == 2
    assert audio.dtype == np.float32
    assert audio.shape == (1000,)
    assert np.allclose(audio, 0.2)


def test_frame_split_across_writes(tmp_path):
    helper = _fake_helper(
        tmp_path,
        """
        header(16000, 2)
        data = struct.pack('<ff', 0.5, -0.1) * 4
        out.write(data[:13]); out.flush(); time.sleep(0.1)
        out.write(data[13:]); out.flush()
        while True: time.sleep(0.05)
        """,
    )
    audio = _record(MacOSCapture(helper=helper))
    assert audio.shape == (4,)
    assert np.allclose(audio, 0.2)


def test_long_recording_is_lossless(tmp_path):
    # Review Focus 1: 10 sn 48 kHz stereo, küçük parçalar halinde
    helper = _fake_helper(
        tmp_path,
        """
        header(48000, 2)
        block = struct.pack('<ff', 0.25, 0.25) * 480
        for _ in range(1000):
            out.write(block)
        out.flush()
        while True: time.sleep(0.05)
        """,
    )
    audio = _record(MacOSCapture(helper=helper), seconds=1.0)
    assert audio.shape == (480_000,)
    assert np.allclose(audio, 0.25)


def test_helper_dies_mid_recording_keeps_audio(tmp_path):
    # Review Focus 2: yardımcı erken çıkarsa yakalanan ses korunur, stop() hata vermez
    helper = _fake_helper(
        tmp_path,
        """
        header(16000, 1)
        out.write(struct.pack('<f', 0.3) * 500); out.flush()
        sys.exit(1)
        """,
    )
    audio = _record(MacOSCapture(helper=helper))
    assert audio.shape == (500,)
    assert np.allclose(audio, 0.3)


def test_permission_denied_raises(tmp_path):
    helper = _fake_helper(
        tmp_path,
        """
        sys.stderr.write('audio_tap: process tap oluşturulamadı (OSStatus 1)\\n')
        sys.exit(77)
        """,
    )
    with pytest.raises(CapturePermissionError):
        MacOSCapture(helper=helper).start()


def test_other_start_failure_raises_runtime_error(tmp_path):
    helper = _fake_helper(tmp_path, "sys.exit(1)\n")
    with pytest.raises(RuntimeError):
        MacOSCapture(helper=helper).start()


def test_missing_helper_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        MacOSCapture(helper=tmp_path / "yok")


def test_stop_without_start_raises(tmp_path):
    helper = _fake_helper(tmp_path, "header(16000, 1)\n")
    with pytest.raises(RuntimeError):
        MacOSCapture(helper=helper).stop()
```

- [ ] **Step 3: Testlerin başarısız olduğunu gör**

Run: `.venv/bin/python -m pytest tests/test_capture_macos.py -v`
Expected: FAIL (`MacOSCapture()` `helper` parametresini tanımıyor / BlackHole arıyor).

- [ ] **Step 4: `src/audio/capture_macos.py`'yi yeniden yaz**

```python
"""macOS sistem sesi yakalama: Core Audio Process Tap (macOS 14.4+, sürücü gerekmez).

Ses, `audio_tap` yardımcısı (tools/audio_tap.swift) tarafından yakalanır ve
stdout'undan ham float32 interleaved PCM olarak okunur. Kullanıcının ses
çıkışı değişmez. İlk kayıtta macOS "sistem sesi kaydı" izni ister.

Bellek için ses okunurken mono'ya indirilir (1 saatlik 48 kHz kayıt ~690 MB).
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np

from .platform_detect import CapturePermissionError

_PERMISSION_EXIT_CODE = 77
_READ_SIZE = 64 * 1024


def _default_helper() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller paketi: Contents/Frameworks
        return Path(sys._MEIPASS) / "audio_tap"
    return Path(__file__).resolve().parents[2] / "tools" / "audio_tap"


class MacOSCapture:
    def __init__(self, helper: str | Path | None = None) -> None:
        self._helper = Path(helper) if helper else _default_helper()
        if not self._helper.exists():
            raise FileNotFoundError(
                f"audio_tap bulunamadı: {self._helper}\n"
                "Derle: swiftc -O -target arm64-apple-macos14.4 tools/audio_tap.swift -o tools/audio_tap"
            )
        self.samplerate = 48_000
        self.channels = 2
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._chunks: list[np.ndarray] = []

    def device_hint(self) -> str:
        return f"Sistem sesi (Core Audio Process Tap) @ {self.samplerate} Hz, {self.channels} kanal"

    def start(self) -> None:
        self._chunks = []
        proc = subprocess.Popen(
            [str(self._helper)],
            stdin=subprocess.PIPE,  # açık tutulur; kapanınca yardımcı kendini temizler
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        header = proc.stderr.readline()
        try:
            fmt = json.loads(header)
        except ValueError:
            code = proc.wait(timeout=5)
            message = (header + proc.stderr.read()).decode(errors="replace").strip()
            if code == _PERMISSION_EXIT_CODE:
                raise CapturePermissionError(message or "sistem sesi izni verilmedi") from None
            raise RuntimeError(f"audio_tap başlatılamadı (kod {code}): {message}") from None
        self.samplerate = int(fmt["samplerate"])
        self.channels = int(fmt["channels"])
        self._proc = proc
        self._reader = threading.Thread(target=self._read_loop, args=(proc,), daemon=True)
        self._reader.start()

    def _read_loop(self, proc: subprocess.Popen) -> None:
        frame_bytes = 4 * self.channels
        pending = b""
        while chunk := proc.stdout.read1(_READ_SIZE):
            data = pending + chunk
            usable = len(data) - len(data) % frame_bytes
            pending = data[usable:]
            if usable:
                frames = np.frombuffer(data[:usable], dtype="<f4").reshape(-1, self.channels)
                self._chunks.append(frames.mean(axis=1, dtype=np.float32))

    def stop(self) -> np.ndarray:
        if self._proc is None:
            raise RuntimeError("start() çağrılmadan stop() çağrıldı")
        proc, self._proc = self._proc, None
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        self._reader.join(timeout=5)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            stream.close()
        chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32, copy=False)
```

- [ ] **Step 5: Testleri çalıştır**

Run: `.venv/bin/python -m pytest tests/test_capture_macos.py -v`
Expected: 8 test PASS.

- [ ] **Step 6: Gerçek yardımcıyla e2e testi ekle** (`tests/test_e2e_macos.py`; Task 5'te genişletilecek)

```python
"""Gerçek audio_tap ile uçtan uca testler. Hoparlörden ses çalar: pytest -m e2e"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(sys.platform != "darwin", reason="yalnızca macOS"),
]

_HELPER = Path(__file__).resolve().parents[1] / "tools" / "audio_tap"
SENTENCE = "Bugün toplantıda bütçeyi konuştuk"


def _say(text: str) -> None:
    if shutil.which("say") is None:
        pytest.skip("say komutu yok")
    subprocess.run(["say", "-v", "Yelda", text], check=True)


def record_sentence():
    from src.audio.capture_macos import MacOSCapture

    if not _HELPER.exists():
        pytest.skip("tools/audio_tap derlenmemiş")
    capture = MacOSCapture()
    capture.start()
    time.sleep(0.5)
    _say(SENTENCE)
    time.sleep(0.5)
    return capture.stop(), capture.samplerate


def test_captures_system_audio():
    audio, samplerate = record_sentence()
    assert audio.size / samplerate > 2.0
    assert float(np.abs(audio).max()) > 0.01
```

- [ ] **Step 7: e2e testini çalıştır**

Run: `swiftc -O -target arm64-apple-macos14.4 tools/audio_tap.swift -o tools/audio_tap && .venv/bin/python -m pytest -m e2e tests/test_e2e_macos.py -v`
Expected: PASS (cümle hoparlörden duyulur).

- [ ] **Step 8: Commit**

```bash
git add src/audio/platform_detect.py src/audio/capture_macos.py tests/test_capture_macos.py tests/test_e2e_macos.py
git commit -m "feat(macos): MacOSCapture BlackHole yerine audio_tap kullanıyor"
```

---

### Task 3: Klasörler (`paths`) ve loglama

**Files:**
- Create: `src/app/__init__.py` (boş), `src/app/paths.py`, `src/app/logging_setup.py`
- Test: `tests/test_paths.py`, `tests/test_logging_setup.py`

**Interfaces:**
- Produces:
  - `src.app.paths.APP_NAME = "Transkript"`
  - `src.app.paths.AppPaths` (frozen dataclass): `models: Path`, `output: Path`, `logs: Path`, `state: Path`; `ensure() -> AppPaths` (klasörleri oluşturur, kendini döndürür)
  - `src.app.paths.is_frozen() -> bool`
  - `src.app.paths.resolve(frozen: bool | None = None, platform: str | None = None, home: Path | None = None, env: Mapping[str, str] | None = None) -> AppPaths`
  - `src.app.logging_setup.setup_logging(log_dir: Path) -> logging.Handler` (eklenen dosya handler'ını döndürür; log dosyası `log_dir / "transkript.log"`)

- [ ] **Step 1: Başarısız testleri yaz** (`tests/test_paths.py`)

```python
from pathlib import Path

from src.app import paths


def test_source_checkout_uses_project_dirs():
    p = paths.resolve(frozen=False)
    root = Path(paths.__file__).resolve().parents[2]
    assert p.models == root / "models"
    assert p.output == root / "output"
    assert p.logs == root / "logs"
    assert p.state == root / ".state"


def test_frozen_macos_uses_user_dirs():
    home = Path("/Users/mudur")
    p = paths.resolve(frozen=True, platform="darwin", home=home, env={})
    assert p.models == home / "Library/Application Support/Transkript/models"
    assert p.output == home / "Documents/Transkriptler"
    assert p.logs == home / "Library/Logs/Transkript"
    assert p.state == home / "Library/Application Support/Transkript"


def test_frozen_windows_uses_localappdata():
    home = Path("C:/Users/mudur")
    env = {"LOCALAPPDATA": "C:/Users/mudur/AppData/Local"}
    p = paths.resolve(frozen=True, platform="win32", home=home, env=env)
    assert p.models == Path("C:/Users/mudur/AppData/Local/Transkript/models")
    assert p.output == home / "Documents/Transkriptler"
    assert p.logs == Path("C:/Users/mudur/AppData/Local/Transkript/logs")


def test_ensure_creates_dirs(tmp_path):
    p = paths.AppPaths(
        models=tmp_path / "m", output=tmp_path / "o", logs=tmp_path / "l", state=tmp_path / "s"
    )
    assert p.ensure() is p
    for d in (p.models, p.output, p.logs, p.state):
        assert d.is_dir()
```

`tests/test_logging_setup.py`:

```python
import logging

from src.app.logging_setup import setup_logging


def test_writes_to_log_file(tmp_path):
    handler = setup_logging(tmp_path / "logs")
    try:
        logging.getLogger("deneme").warning("Merhaba günlük")
        handler.flush()
        text = (tmp_path / "logs" / "transkript.log").read_text(encoding="utf-8")
        assert "Merhaba günlük" in text
        assert "WARNING" in text
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()
```

- [ ] **Step 2: Başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_paths.py tests/test_logging_setup.py -v`
Expected: FAIL (`ModuleNotFoundError: src.app`).

- [ ] **Step 3: `src/app/__init__.py` (boş) ve `src/app/paths.py` yaz**

```python
"""Uygulamanın kullandığı klasörler.

Paketli uygulamada (PyInstaller, sys.frozen) kullanıcı klasörleri, kaynaktan
çalışırken proje içi klasörler kullanılır; böylece geliştiricinin indirdiği
model ve çıktılar yerinde kalır.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Transkript"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AppPaths:
    models: Path
    output: Path
    logs: Path
    state: Path  # küçük ayar / işaret dosyaları

    def ensure(self) -> "AppPaths":
        for directory in (self.models, self.output, self.logs, self.state):
            directory.mkdir(parents=True, exist_ok=True)
        return self


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resolve(
    frozen: bool | None = None,
    platform: str | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> AppPaths:
    frozen = is_frozen() if frozen is None else frozen
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else home
    env = os.environ if env is None else env

    if not frozen:
        return AppPaths(
            models=_PROJECT_ROOT / "models",
            output=_PROJECT_ROOT / "output",
            logs=_PROJECT_ROOT / "logs",
            state=_PROJECT_ROOT / ".state",
        )
    output = home / "Documents" / "Transkriptler"
    if platform == "darwin":
        support = home / "Library" / "Application Support" / APP_NAME
        return AppPaths(models=support / "models", output=output,
                        logs=home / "Library" / "Logs" / APP_NAME, state=support)
    if platform == "win32":
        local = Path(env.get("LOCALAPPDATA", str(home / "AppData" / "Local"))) / APP_NAME
        return AppPaths(models=local / "models", output=output, logs=local / "logs", state=local)
    data = Path(env.get("XDG_DATA_HOME", str(home / ".local" / "share"))) / APP_NAME
    return AppPaths(models=data / "models", output=output, logs=data / "logs", state=data)
```

- [ ] **Step 4: `src/app/logging_setup.py` yaz**

```python
"""Dönen log dosyası ve yakalanmamış hataların kaydı.

Kullanıcıya teknik ayrıntı gösterilmez; tüm ayrıntı buraya yazılır ve menüdeki
"Hata Kaydını Göster" ile bu klasör açılır.
"""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path) -> logging.Handler:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "transkript.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    def _log_uncaught(exc_type, exc, tb):
        root.critical("Yakalanmamış hata", exc_info=(exc_type, exc, tb))

    def _log_thread(args):
        root.critical("Thread hatası (%s)", args.thread.name if args.thread else "?",
                      exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = _log_uncaught
    threading.excepthook = _log_thread
    return handler
```

- [ ] **Step 5: Testleri çalıştır**

Run: `.venv/bin/python -m pytest tests/test_paths.py tests/test_logging_setup.py -v`
Expected: 5 test PASS.

- [ ] **Step 6: Commit**

```bash
git add src/app/__init__.py src/app/paths.py src/app/logging_setup.py tests/test_paths.py tests/test_logging_setup.py
git commit -m "feat(app): paketli/kaynak klasör çözümü ve dönen log dosyası"
```

---

### Task 4: Model yöneticisi (ilerlemeli, atomik indirme)

**Files:**
- Create: `src/app/model_manager.py`
- Test: `tests/test_model_manager.py`

**Interfaces:**
- Produces:
  - `MODEL_REPO = "Systran/faster-whisper-medium"`, `MODEL_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")`
  - `class ModelDownloadError(RuntimeError)`, `class DiskFullError(ModelDownloadError)`
  - `class Fetcher(Protocol)`: `size(url: str) -> int`, `stream(url: str) -> Iterator[bytes]`; hatada `ModelDownloadError` fırlatır.
  - `class HttpxFetcher` (gerçek uygulama)
  - `class ModelManager(models_dir: Path, repo: str = MODEL_REPO, files: tuple[str, ...] = MODEL_FILES, fetcher: Fetcher | None = None)`: `model_dir: Path` (= `models_dir / "faster-whisper-medium"`), `is_ready() -> bool`, `download(on_progress: Callable[[float], None]) -> None`

- [ ] **Step 1: Başarısız testleri yaz** (`tests/test_model_manager.py`)

```python
from __future__ import annotations

import errno
import shutil
from collections import namedtuple

import pytest

from src.app.model_manager import DiskFullError, ModelDownloadError, ModelManager

FILES = ("config.json", "model.bin")
CONTENT = {"config.json": b'{"a": 1}', "model.bin": b"x" * 5000}


class FakeFetcher:
    def __init__(self, content=CONTENT, fail_on=None, truncate=None, oserror=None):
        self.content = content
        self.fail_on = fail_on
        self.truncate = truncate
        self.oserror = oserror

    def _name(self, url):
        return url.rsplit("/", 1)[1]

    def size(self, url):
        return len(self.content[self._name(url)])

    def stream(self, url):
        name = self._name(url)
        data = self.content[name]
        if name == self.truncate:
            data = data[: len(data) // 2]
        for i in range(0, len(data), 1000):
            if name == self.fail_on and i >= 2000:
                raise ModelDownloadError("bağlantı koptu")
            if name == self.oserror and i >= 2000:
                raise OSError(errno.ENOSPC, "No space left on device")
            yield data[i : i + 1000]


def _manager(tmp_path, **kw):
    return ModelManager(tmp_path / "models", repo="Systran/faster-whisper-medium",
                        files=FILES, fetcher=FakeFetcher(**kw))


def test_model_dir_name(tmp_path):
    assert _manager(tmp_path).model_dir == tmp_path / "models" / "faster-whisper-medium"


def test_download_success(tmp_path):
    m = _manager(tmp_path)
    assert not m.is_ready()
    progress = []
    m.download(progress.append)
    assert m.is_ready()
    for name, data in CONTENT.items():
        assert (m.model_dir / name).read_bytes() == data
    assert progress[0] == 0.0
    assert progress[-1] == 1.0
    assert progress == sorted(progress)
    assert not list((tmp_path / "models").glob("*.partial"))


def test_network_failure_leaves_nothing(tmp_path):
    m = _manager(tmp_path, fail_on="model.bin")
    with pytest.raises(ModelDownloadError):
        m.download(lambda p: None)
    assert not m.is_ready()
    assert not m.model_dir.exists()
    assert not list((tmp_path / "models").glob("*.partial"))


def test_truncated_stream_is_error(tmp_path):
    m = _manager(tmp_path, truncate="model.bin")
    with pytest.raises(ModelDownloadError):
        m.download(lambda p: None)
    assert not m.is_ready()


def test_enospc_while_writing_is_disk_full(tmp_path):
    m = _manager(tmp_path, oserror="model.bin")
    with pytest.raises(DiskFullError):
        m.download(lambda p: None)
    assert not list((tmp_path / "models").glob("*.partial"))


def test_not_enough_free_space_up_front(tmp_path, monkeypatch):
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda p: Usage(10_000, 9_000, 100))
    m = _manager(tmp_path)
    with pytest.raises(DiskFullError):
        m.download(lambda p: None)
    assert not list((tmp_path / "models").glob("*.partial"))


def test_redownload_replaces_previous_partial(tmp_path):
    m = _manager(tmp_path)
    stale = tmp_path / "models" / "faster-whisper-medium.partial"
    stale.mkdir(parents=True)
    (stale / "model.bin").write_bytes(b"eski")
    m.download(lambda p: None)
    assert m.is_ready()
    assert not stale.exists()
```

- [ ] **Step 2: Başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_model_manager.py -v`
Expected: FAIL (`ModuleNotFoundError: src.app.model_manager`).

- [ ] **Step 3: `src/app/model_manager.py` yaz**

```python
"""Whisper modelinin varlığını kontrol eder, yoksa ilerleme bildirerek indirir.

Model, Hugging Face'teki CTranslate2 dönüştürülmüş sürümden (Systran) düz bir
klasöre indirilir; faster-whisper bu klasörü doğrudan yükleyebilir. İndirme
önce `<ad>.partial` klasörüne yapılır ve tüm dosyalar eksiksiz inince yerine
taşınır; böylece yarım model hiçbir zaman "hazır" görünmez.
"""

from __future__ import annotations

import errno
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Protocol

MODEL_REPO = "Systran/faster-whisper-medium"
MODEL_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
_URL = "https://huggingface.co/{repo}/resolve/main/{name}"
_CHUNK = 1 << 20


class ModelDownloadError(RuntimeError):
    """Model indirilemedi (ağ, sunucu, eksik veri)."""


class DiskFullError(ModelDownloadError):
    """Diskte model için yeterli yer yok."""


class Fetcher(Protocol):
    def size(self, url: str) -> int: ...
    def stream(self, url: str) -> Iterator[bytes]: ...


class HttpxFetcher:
    def __init__(self, timeout: float = 30.0) -> None:
        import httpx

        self._httpx = httpx
        self._client = httpx.Client(follow_redirects=True, timeout=timeout)

    def size(self, url: str) -> int:
        try:
            response = self._client.head(url)
            response.raise_for_status()
            return int(response.headers["content-length"])
        except (self._httpx.HTTPError, KeyError, ValueError) as exc:
            raise ModelDownloadError(f"{url}: {exc}") from exc

    def stream(self, url: str) -> Iterator[bytes]:
        try:
            with self._client.stream("GET", url) as response:
                response.raise_for_status()
                yield from response.iter_bytes(_CHUNK)
        except self._httpx.HTTPError as exc:
            raise ModelDownloadError(f"{url}: {exc}") from exc


class ModelManager:
    def __init__(
        self,
        models_dir: Path,
        repo: str = MODEL_REPO,
        files: tuple[str, ...] = MODEL_FILES,
        fetcher: Fetcher | None = None,
    ) -> None:
        self._repo = repo
        self._files = files
        self._fetcher = fetcher
        self.model_dir = models_dir / repo.split("/", 1)[1]

    def is_ready(self) -> bool:
        return all((self.model_dir / name).is_file() for name in self._files)

    def download(self, on_progress: Callable[[float], None]) -> None:
        partial = self.model_dir.with_name(self.model_dir.name + ".partial")
        shutil.rmtree(partial, ignore_errors=True)
        partial.mkdir(parents=True)
        try:
            self._download_into(partial, on_progress)
        except OSError as exc:
            shutil.rmtree(partial, ignore_errors=True)
            if exc.errno == errno.ENOSPC:
                raise DiskFullError(str(exc)) from exc
            raise ModelDownloadError(str(exc)) from exc
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
        shutil.rmtree(self.model_dir, ignore_errors=True)
        partial.rename(self.model_dir)

    def _download_into(self, target: Path, on_progress: Callable[[float], None]) -> None:
        fetcher = self._fetcher or HttpxFetcher()
        urls = {name: _URL.format(repo=self._repo, name=name) for name in self._files}
        sizes = {name: fetcher.size(url) for name, url in urls.items()}
        total = sum(sizes.values())
        free = shutil.disk_usage(target).free
        if free < total:
            raise DiskFullError(f"{total} bayt gerekli, {free} bayt boş")

        done = 0
        on_progress(0.0)
        for name, url in urls.items():
            written = 0
            with open(target / name, "wb") as out:
                for chunk in fetcher.stream(url):
                    out.write(chunk)
                    written += len(chunk)
                    done += len(chunk)
                    on_progress(min(done / total, 1.0) if total else 1.0)
            if written != sizes[name]:
                raise ModelDownloadError(f"{name}: eksik indirme ({written}/{sizes[name]} bayt)")
        on_progress(1.0)
```

- [ ] **Step 4: Testleri çalıştır**

Run: `.venv/bin/python -m pytest tests/test_model_manager.py -v`
Expected: 7 test PASS.

- [ ] **Step 5: Gerçek indirmeyi küçük modelle dene** (ağ gerektirir, ~75 MB)

Run:
```bash
.venv/bin/python -c "
from pathlib import Path
from src.app.model_manager import ModelManager
m = ModelManager(Path('build/models'), repo='Systran/faster-whisper-tiny')
m.download(lambda p: print(f'\r%{int(p*100)}', end='', flush=True))
print(); print(m.is_ready(), sorted(x.name for x in m.model_dir.iterdir()))
"
```
Expected: ilerleme %0'dan %100'e çıkar, ardından `True ['config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt']`. (`build/` gitignore'da.)

- [ ] **Step 6: Commit**

```bash
git add src/app/model_manager.py tests/test_model_manager.py
git commit -m "feat(app): ilerlemeli ve atomik Whisper model indirici"
```

---

### Task 5: `WhisperEngine` ilerleme bildirsin + gerçek transkript e2e

**Files:**
- Modify: `src/transcribe/whisper_engine.py` (`transcribe` metodu)
- Test: `tests/test_whisper_engine.py`
- Modify: `tests/test_e2e_macos.py`

**Interfaces:**
- Consumes: `ModelManager.model_dir` (Task 4) e2e testinde.
- Produces: `WhisperEngine.transcribe(audio_path: str | Path, language: str | None = None, on_progress: Callable[[float], None] | None = None) -> TranscriptResult`. `on_progress` 0.0-1.0 arası, monoton, son çağrı 1.0. `WhisperEngine(model_size=<klasör yolu>)` düz model klasörünü yükler (faster-whisper'ın kendi davranışı).

- [ ] **Step 1: Başarısız testi yaz** (`tests/test_whisper_engine.py`)

```python
from types import SimpleNamespace

from src.transcribe.whisper_engine import WhisperEngine


class FakeModel:
    def transcribe(self, path, language=None, vad_filter=True):
        segments = [
            SimpleNamespace(start=0.0, end=2.5, text=" Merhaba."),
            SimpleNamespace(start=2.5, end=7.5, text=" Bütçe."),
        ]
        info = SimpleNamespace(language="tr", language_probability=0.99, duration=10.0)
        return iter(segments), info


def _engine():
    engine = object.__new__(WhisperEngine)  # ağır model yüklemesini atla
    engine.model_size = "fake"
    engine._model = FakeModel()
    return engine


def test_progress_reports_segment_end_over_duration():
    progress = []
    result = _engine().transcribe("x.wav", on_progress=progress.append)
    assert progress == [0.25, 0.75, 1.0]
    assert [s.text for s in result.segments] == [" Merhaba.", " Bütçe."]
    assert result.language == "tr"


def test_progress_is_optional():
    assert len(_engine().transcribe("x.wav").segments) == 2
```

- [ ] **Step 2: Başarısız olduğunu gör**

Run: `.venv/bin/python -m pytest tests/test_whisper_engine.py -v`
Expected: FAIL (`unexpected keyword argument 'on_progress'`).

- [ ] **Step 3: `transcribe` metodunu değiştir.** `src/transcribe/whisper_engine.py` başına `from collections.abc import Callable` ekle; `transcribe` metodunu şununla değiştir:

```python
    def transcribe(
        self,
        audio_path: str | Path,
        language: str | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> TranscriptResult:
        """Ses dosyasını transkript eder.

        language None ise Whisper dili otomatik algılar (Türkçe dahil).
        on_progress verilirse 0.0-1.0 arası ilerleme bildirilir (segment sonu / ses süresi).
        """
        segments_iter, info = self._model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,  # sessiz bölümleri atla (toplantılarda uzun boşluklar olur)
        )
        segments = []
        for s in segments_iter:
            segments.append(Segment(start=s.start, end=s.end, text=s.text))
            if on_progress and info.duration:
                on_progress(min(s.end / info.duration, 1.0))
        if on_progress:
            on_progress(1.0)
        return TranscriptResult(
            segments=segments,
            language=info.language,
            language_probability=info.language_probability,
        )
```

- [ ] **Step 4: Testleri çalıştır**

Run: `.venv/bin/python -m pytest tests/test_whisper_engine.py tests/test_writer.py -v`
Expected: PASS.

- [ ] **Step 5: Geliştirici modelini yeni klasör düzenine taşı** (bir kerelik, tekrar indirmemek için)

Run:
```bash
mkdir -p models/faster-whisper-medium
cp -L models/models--Systran--faster-whisper-medium/snapshots/*/* models/faster-whisper-medium/
ls -la models/faster-whisper-medium
```
Expected: 4 dosya, `model.bin` ~1.5 GB. (Eski HF önbelleği Task 8'de CLI da yeni klasörü kullanınca silinecek.)

- [ ] **Step 6: Gerçek transkript e2e testini ekle.** `tests/test_e2e_macos.py` sonuna:

```python
def test_records_and_transcribes_turkish_sentence(tmp_path):
    import soundfile as sf

    from src.app.model_manager import ModelManager
    from src.app.paths import resolve
    from src.transcribe.whisper_engine import WhisperEngine

    manager = ModelManager(resolve(frozen=False).models)
    if not manager.is_ready():
        pytest.skip("models/faster-whisper-medium hazır değil")
    audio, samplerate = record_sentence()
    wav = tmp_path / "kayit.wav"
    sf.write(wav, audio, samplerate)
    result = WhisperEngine(model_size=str(manager.model_dir)).transcribe(wav)
    text = result.text.lower()
    assert "toplantı" in text
    assert "bütçe" in text
```

- [ ] **Step 7: e2e testini çalıştır**

Run: `.venv/bin/python -m pytest -m e2e tests/test_e2e_macos.py -v`
Expected: 2 test PASS.

- [ ] **Step 8: Commit**

```bash
git add src/transcribe/whisper_engine.py tests/test_whisper_engine.py tests/test_e2e_macos.py
git commit -m "feat(transcribe): transkript ilerlemesi ve audio_tap ile uçtan uca Türkçe testi"
```

---

### Task 6: Uygulama çekirdeği (`Controller`)

**Files:**
- Create: `src/app/controller.py`
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: `ModelManager` (`model_dir`, `is_ready()`, `download(on_progress)`), `DiskFullError`, `ModelDownloadError` (Task 4); `CapturePermissionError` (Task 2); `WhisperEngine.transcribe(..., on_progress=)` (Task 5); `write_txt`, `write_srt` (mevcut).
- Produces:
  - `Phase` enum: `NEEDS_MODEL, DOWNLOADING, IDLE, RECORDING, TRANSCRIBING, ERROR`
  - `ErrorKind` enum: `NETWORK, DISK`
  - `State` (frozen dataclass): `phase: Phase`, `progress: float | None = None`, `started_at: float | None = None`, `error: ErrorKind | None = None`
  - `Listener` Protocol: `on_state(state: State)`, `on_message(title: str, body: str)`, `on_transcript_ready(txt_path: Path)`
  - `Controller(*, capture_factory: Callable[[], Capture], engine_factory: Callable[[Path], Engine], model_manager, output_dir: Path, listener: Listener, silence_hint: str = "", run_in_background: Callable[[Callable[[], None]], None] = <thread>, clock: Callable[[], float] = time.monotonic, now: Callable[[], datetime] = datetime.now)`
  - Metotlar: `state` (property), `start()`, `toggle()`, `retry_download()`, `shutdown()`, `latest_transcript() -> Path | None`

- [ ] **Step 1: Başarısız testleri yaz** (`tests/test_controller.py`)

```python
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from src.app.controller import Controller, ErrorKind, Phase
from src.app.model_manager import DiskFullError, ModelDownloadError
from src.audio.platform_detect import CapturePermissionError
from src.transcribe.whisper_engine import Segment, TranscriptResult

SPEECH = (np.sin(np.linspace(0, 200, 16000)) * 0.3).astype(np.float32)


class FakeCapture:
    def __init__(self, audio=SPEECH, start_error=None):
        self.samplerate = 16000
        self.audio = audio
        self.start_error = start_error
        self.started = False

    def start(self):
        if self.start_error:
            raise self.start_error
        self.started = True

    def stop(self):
        return self.audio


class FakeEngine:
    def __init__(self, segments=None, error=None, progress=(0.5,)):
        self.segments = [Segment(0.0, 1.0, " Bütçeyi konuştuk.")] if segments is None else segments
        self.error = error
        self.progress = progress
        self.calls = []

    def transcribe(self, path, language=None, on_progress=None):
        self.calls.append(Path(path))
        if self.error:
            raise self.error
        for p in self.progress:
            on_progress(p)
        on_progress(1.0)
        return TranscriptResult(segments=self.segments, language="tr", language_probability=0.9)


class FakeModelManager:
    def __init__(self, tmp_path, ready=True, errors=()):
        self.model_dir = tmp_path / "model"
        self.ready = ready
        self.errors = list(errors)

    def is_ready(self):
        return self.ready

    def download(self, on_progress):
        on_progress(0.0)
        on_progress(0.4)
        if self.errors:
            raise self.errors.pop(0)
        on_progress(1.0)
        self.ready = True


class Listener:
    def __init__(self):
        self.states, self.messages, self.ready = [], [], []

    def on_state(self, s):
        self.states.append(s)

    def on_message(self, title, body):
        self.messages.append((title, body))

    def on_transcript_ready(self, p):
        self.ready.append(p)


class ManualRunner:
    def __init__(self):
        self.jobs = []

    def __call__(self, fn):
        self.jobs.append(fn)

    def run_all(self):
        while self.jobs:
            self.jobs.pop(0)()


@pytest.fixture
def env(tmp_path):
    class Env:
        pass

    e = Env()
    e.tmp = tmp_path
    e.capture = FakeCapture()
    e.engine = FakeEngine()
    e.models = FakeModelManager(tmp_path)
    e.listener = Listener()
    e.runner = ManualRunner()
    e.engine_dirs = []

    def engine_factory(model_dir):
        e.engine_dirs.append(model_dir)
        return e.engine

    def make(**overrides):
        kwargs = dict(
            capture_factory=lambda: e.capture,
            engine_factory=engine_factory,
            model_manager=e.models,
            output_dir=tmp_path / "out",
            listener=e.listener,
            silence_hint="İpucu.",
            run_in_background=e.runner,
            clock=lambda: 100.0,
            now=lambda: datetime(2026, 10, 6, 14, 30, 0),
        )
        kwargs.update(overrides)
        return Controller(**kwargs)

    e.make = make
    return e


def test_start_with_ready_model_goes_idle(env):
    c = env.make()
    c.start()
    assert c.state.phase is Phase.IDLE


def test_start_without_model_downloads_then_idle(env):
    env.models.ready = False
    c = env.make()
    c.start()
    assert c.state.phase is Phase.DOWNLOADING
    env.runner.run_all()
    assert c.state.phase is Phase.IDLE
    progresses = [s.progress for s in env.listener.states if s.phase is Phase.DOWNLOADING]
    assert progresses == [0.0, 0.4, 1.0]
    assert env.listener.messages[-1][0] == "Hazır"


def test_network_error_then_retry(env):
    env.models.ready = False
    env.models.errors = [ModelDownloadError("koptu")]
    c = env.make()
    c.start()
    env.runner.run_all()
    assert c.state.phase is Phase.ERROR
    assert c.state.error is ErrorKind.NETWORK
    assert env.listener.messages[-1][0] == "Model indirilemedi"
    c.retry_download()
    env.runner.run_all()
    assert c.state.phase is Phase.IDLE


def test_disk_full_error(env):
    env.models.ready = False
    env.models.errors = [DiskFullError("dolu")]
    c = env.make()
    c.start()
    env.runner.run_all()
    assert c.state.error is ErrorKind.DISK
    assert env.listener.messages[-1][0] == "Diskte yeterli yer yok"


def test_toggle_starts_recording(env):
    c = env.make()
    c.start()
    c.toggle()
    assert c.state.phase is Phase.RECORDING
    assert c.state.started_at == 100.0
    assert env.capture.started


def test_full_flow_writes_outputs_and_notifies(env):
    c = env.make()
    c.start()
    c.toggle()
    c.toggle()
    assert c.state.phase is Phase.TRANSCRIBING
    assert c.state.progress == 0.0
    env.runner.run_all()
    assert c.state.phase is Phase.IDLE
    out = env.tmp / "out"
    assert (out / "kayit_20261006_143000.wav").is_file()
    txt = out / "kayit_20261006_143000.txt"
    assert txt.read_text(encoding="utf-8").strip() == "Bütçeyi konuştuk."
    assert (out / "kayit_20261006_143000.srt").is_file()
    assert env.listener.ready == [txt]
    assert c.latest_transcript() == txt
    assert env.engine_dirs == [env.models.model_dir]
    progresses = [s.progress for s in env.listener.states if s.phase is Phase.TRANSCRIBING]
    assert progresses == [0.0, 0.5, 1.0]


def test_engine_loaded_once(env):
    c = env.make()
    c.start()
    for _ in range(2):
        c.toggle()
        c.toggle()
        env.runner.run_all()
    assert len(env.engine_dirs) == 1
    assert len(env.engine.calls) == 2


def test_progress_throttled_to_whole_percent(env):
    env.engine.progress = (0.001, 0.002, 0.003, 0.5)
    c = env.make()
    c.start()
    c.toggle()
    c.toggle()
    env.runner.run_all()
    progresses = [s.progress for s in env.listener.states if s.phase is Phase.TRANSCRIBING]
    assert progresses == [0.0, 0.5, 1.0]


def test_silent_recording_skips_transcription(env):
    env.capture.audio = np.zeros(16000, dtype=np.float32)
    c = env.make()
    c.start()
    c.toggle()
    c.toggle()
    assert c.state.phase is Phase.IDLE
    title, body = env.listener.messages[-1]
    assert title == "Kayıtta ses algılanmadı"
    assert body.endswith("İpucu.")
    assert not env.runner.jobs
    assert not (env.tmp / "out").exists()


def test_permission_error_stays_idle(env):
    env.capture.start_error = CapturePermissionError("yok")
    c = env.make()
    c.start()
    c.toggle()
    assert c.state.phase is Phase.IDLE
    assert env.listener.messages[-1][0] == "Sistem sesine izin verilmedi"


def test_unexpected_start_error_stays_idle(env):
    env.capture.start_error = RuntimeError("boom")
    c = env.make()
    c.start()
    c.toggle()
    assert c.state.phase is Phase.IDLE
    assert env.listener.messages[-1][0] == "Kayıt başlatılamadı"


def test_toggle_while_downloading_reports_percent(env):
    env.models.ready = False
    c = env.make()
    c.start()
    c._set_download_progress(0.42)
    c.toggle()
    title, body = env.listener.messages[-1]
    assert title == "Model hazırlanıyor"
    assert "%42" in body


def test_toggle_while_transcribing_is_ignored(env):
    c = env.make()
    c.start()
    c.toggle()
    c.toggle()
    c.toggle()
    assert c.state.phase is Phase.TRANSCRIBING
    assert env.listener.messages[-1][0] == "Transkript sürüyor"


def test_empty_transcript(env):
    env.engine.segments = []
    c = env.make()
    c.start()
    c.toggle()
    c.toggle()
    env.runner.run_all()
    assert c.state.phase is Phase.IDLE
    assert env.listener.messages[-1][0] == "Konuşma algılanamadı"
    assert not list((env.tmp / "out").glob("*.txt"))


def test_engine_failure_keeps_wav(env):
    env.engine.error = RuntimeError("model bozuk")
    c = env.make()
    c.start()
    c.toggle()
    c.toggle()
    env.runner.run_all()
    assert c.state.phase is Phase.IDLE
    assert env.listener.messages[-1][0] == "Bir sorun oluştu"
    assert list((env.tmp / "out").glob("*.wav"))


def test_shutdown_while_recording_saves_wav_without_transcribing(env):
    c = env.make()
    c.start()
    c.toggle()
    c.shutdown()
    assert list((env.tmp / "out").glob("*.wav"))
    assert not env.runner.jobs


def test_latest_transcript_falls_back_to_newest_file(env):
    out = env.tmp / "out"
    out.mkdir()
    old, new = out / "a.txt", out / "b.txt"
    old.write_text("eski")
    new.write_text("yeni")
    os.utime(old, (1, 1))
    c = env.make()
    assert c.latest_transcript() == new


def test_latest_transcript_none_when_empty(env):
    assert env.make().latest_transcript() is None
```

- [ ] **Step 2: Başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_controller.py -v`
Expected: FAIL (`ModuleNotFoundError: src.app.controller`).

- [ ] **Step 3: `src/app/controller.py` yaz**

```python
"""OS ve arayüz bilmeyen uygulama çekirdeği.

Kabuk (macOS menü çubuğu, ileride Windows sistem tepsisi) yalnızca `toggle()`
gibi komutları çağırır ve `Listener` üzerinden gelen durum / mesajları
gösterir. Ağır işler (model indirme, transkript) arka planda çalışır;
Listener callback'leri o thread'lerden çağrılabilir, kabuk bunları kendi
ana thread'ine aktarmakla sorumludur.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Protocol

import numpy as np
import soundfile as sf

from src.app.model_manager import DiskFullError
from src.audio.platform_detect import CapturePermissionError
from src.output.writer import write_srt, write_txt
from src.transcribe.whisper_engine import TranscriptResult

log = logging.getLogger(__name__)

SILENCE_PEAK = 1e-4
_LOG_HINT = "Ayrıntılar için menüden 'Hata Kaydını Göster'."


class Phase(Enum):
    NEEDS_MODEL = "needs_model"
    DOWNLOADING = "downloading"
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    ERROR = "error"


class ErrorKind(Enum):
    NETWORK = "network"
    DISK = "disk"


@dataclass(frozen=True)
class State:
    phase: Phase
    progress: float | None = None  # DOWNLOADING / TRANSCRIBING: 0.0-1.0
    started_at: float | None = None  # RECORDING: clock() değeri
    error: ErrorKind | None = None  # ERROR


class Listener(Protocol):
    def on_state(self, state: State) -> None: ...
    def on_message(self, title: str, body: str) -> None: ...
    def on_transcript_ready(self, txt_path: Path) -> None: ...


class Capture(Protocol):
    samplerate: int

    def start(self) -> None: ...
    def stop(self) -> np.ndarray: ...


class Engine(Protocol):
    def transcribe(self, audio_path, language=None, on_progress=None) -> TranscriptResult: ...


def _run_in_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


class Controller:
    def __init__(
        self,
        *,
        capture_factory: Callable[[], Capture],
        engine_factory: Callable[[Path], Engine],
        model_manager,
        output_dir: Path,
        listener: Listener,
        silence_hint: str = "",
        run_in_background: Callable[[Callable[[], None]], None] = _run_in_thread,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._capture_factory = capture_factory
        self._engine_factory = engine_factory
        self._models = model_manager
        self._output_dir = output_dir
        self._listener = listener
        self._silence_hint = silence_hint
        self._run = run_in_background
        self._clock = clock
        self._now = now
        self._state = State(Phase.NEEDS_MODEL)
        self._capture: Capture | None = None
        self._engine: Engine | None = None
        self._last_transcript: Path | None = None

    @property
    def state(self) -> State:
        return self._state

    def _set(self, state: State) -> None:
        self._state = state
        self._listener.on_state(state)

    def _message(self, title: str, body: str) -> None:
        self._listener.on_message(title, body)

    # --- model ---

    def start(self) -> None:
        if self._models.is_ready():
            self._set(State(Phase.IDLE))
        else:
            self._begin_download()

    def retry_download(self) -> None:
        if self._state.phase in (Phase.ERROR, Phase.NEEDS_MODEL):
            self._begin_download()

    def _begin_download(self) -> None:
        self._set(State(Phase.DOWNLOADING, progress=0.0))
        self._run(self._download_worker)

    def _set_download_progress(self, progress: float) -> None:
        if self._state.phase is not Phase.DOWNLOADING:
            return
        # yalnızca tam yüzde değişince yayınla (1 MB'lık her parçada değil)
        if int(progress * 100) != int((self._state.progress or 0.0) * 100):
            self._set(State(Phase.DOWNLOADING, progress=progress))

    def _download_worker(self) -> None:
        try:
            self._models.download(self._set_download_progress)
        except DiskFullError:
            log.exception("Model indirilemedi: disk dolu")
            self._set(State(Phase.ERROR, error=ErrorKind.DISK))
            self._message("Diskte yeterli yer yok",
                          "Model için yaklaşık 2 GB boş alan gerekiyor. Yer açıp menüden 'Tekrar Dene'ye tıkla.")
            return
        except Exception:
            log.exception("Model indirilemedi")
            self._set(State(Phase.ERROR, error=ErrorKind.NETWORK))
            self._message("Model indirilemedi",
                          "İnternet bağlantını kontrol edip menüden 'Tekrar Dene'ye tıkla.")
            return
        log.info("Model hazır: %s", self._models.model_dir)
        self._set(State(Phase.IDLE))
        self._message("Hazır", "🎙 simgesine tıklayıp kayda başlayabilirsin.")

    # --- kayıt ---

    def toggle(self) -> None:
        phase = self._state.phase
        if phase is Phase.IDLE:
            self._start_recording()
        elif phase is Phase.RECORDING:
            self._stop_recording()
        elif phase is Phase.DOWNLOADING:
            pct = int((self._state.progress or 0.0) * 100)
            self._message("Model hazırlanıyor", f"Model indiriliyor (%{pct}). Bitince kayıt yapabilirsin.")
        elif phase is Phase.TRANSCRIBING:
            self._message("Transkript sürüyor", "Önceki kayıt hâlâ metne çevriliyor. Bitince yeni kayıt başlatabilirsin.")
        else:
            self._message("Model hazır değil", "Menüden 'Tekrar Dene' ile modeli indir.")

    def _start_recording(self) -> None:
        try:
            capture = self._capture_factory()
            capture.start()
        except CapturePermissionError:
            log.warning("Sistem sesi izni yok", exc_info=True)
            self._message("Sistem sesine izin verilmedi", "Menüden sistem sesi iznini açıp tekrar dene.")
            return
        except Exception:
            log.exception("Kayıt başlatılamadı")
            self._message("Kayıt başlatılamadı", f"Bir sorun oluştu. {_LOG_HINT}")
            return
        self._capture = capture
        log.info("Kayıt başladı")
        self._set(State(Phase.RECORDING, started_at=self._clock()))

    def _stop_recording(self) -> None:
        try:
            wav = self._save_recording()
        except Exception:
            log.exception("Kayıt durdurulamadı")
            self._set(State(Phase.IDLE))
            self._message("Bir sorun oluştu", f"Kayıt kaydedilemedi. {_LOG_HINT}")
            return
        if wav is None:
            return
        self._set(State(Phase.TRANSCRIBING, progress=0.0))
        self._run(lambda: self._transcribe_worker(wav))

    def _save_recording(self) -> Path | None:
        """Kaydı durdurur ve WAV'ı yazar. Sessizse None döner ve IDLE'a geçer."""
        capture, self._capture = self._capture, None
        audio = capture.stop()
        if audio.size == 0 or float(np.abs(audio).max()) < SILENCE_PEAK:
            log.info("Sessiz kayıt (%d örnek)", audio.size)
            self._set(State(Phase.IDLE))
            body = "Kayıt süresince bilgisayardan ses gelmedi."
            self._message("Kayıtta ses algılanmadı", f"{body} {self._silence_hint}".strip())
            return None
        self._output_dir.mkdir(parents=True, exist_ok=True)
        wav = self._output_dir / f"kayit_{self._now():%Y%m%d_%H%M%S}.wav"
        sf.write(wav, audio, capture.samplerate)
        log.info("Kayıt yazıldı: %s (%.1f sn)", wav, audio.size / capture.samplerate)
        return wav

    def _transcribe_worker(self, wav: Path) -> None:
        last_pct = 0

        def progress(p: float) -> None:
            nonlocal last_pct
            pct = int(p * 100)
            if pct != last_pct:
                last_pct = pct
                self._set(State(Phase.TRANSCRIBING, progress=p))

        try:
            if self._engine is None:
                self._engine = self._engine_factory(self._models.model_dir)
            result = self._engine.transcribe(wav, on_progress=progress)
            if not result.segments:
                self._message("Konuşma algılanamadı", "Kayıtta metne çevrilecek konuşma bulunamadı.")
                return
            txt = write_txt(result, wav.with_suffix(".txt"))
            write_srt(result, wav.with_suffix(".srt"))
            self._last_transcript = txt
            log.info("Transkript hazır: %s (%s, %d segment)", txt, result.language, len(result.segments))
            self._listener.on_transcript_ready(txt)
        except Exception:
            log.exception("Transkript üretilemedi: %s", wav)
            self._message("Bir sorun oluştu", f"Transkript üretilemedi; ses kaydı klasörde duruyor. {_LOG_HINT}")
        finally:
            self._set(State(Phase.IDLE))

    # --- diğer ---

    def shutdown(self) -> None:
        """Uygulama kapanırken çağrılır. Kayıt sürüyorsa ses diske yazılır (transkript edilmez)."""
        if self._state.phase is Phase.RECORDING:
            try:
                self._save_recording()
            except Exception:
                log.exception("Kapanışta kayıt kaydedilemedi")

    def latest_transcript(self) -> Path | None:
        if self._last_transcript and self._last_transcript.exists():
            return self._last_transcript
        if not self._output_dir.exists():
            return None
        candidates = sorted(self._output_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime)
        return candidates[-1] if candidates else None
```

Not: `test_progress_throttled_to_whole_percent` beklentisi `[0.0, 0.5, 1.0]`: 0.001-0.003 tam yüzde 0'dır ve başlangıçtaki 0.0 ile aynı olduğu için yayınlanmaz.

- [ ] **Step 4: Testleri çalıştır**

Run: `.venv/bin/python -m pytest tests/test_controller.py -v`
Expected: 19 test PASS.

- [ ] **Step 5: Commit**

```bash
git add src/app/controller.py tests/test_controller.py
git commit -m "feat(app): OS bilmeyen kayıt/transkript durum makinesi"
```

---

### Task 7: Menü çubuğu kabuğu, bildirimler, oturum açılışında başlatma; eski dosyaları kaldır

**Files:**
- Create: `src/ui/__init__.py` (boş), `src/ui/status_text.py`, `src/ui/macos_system.py`, `src/ui/menubar_macos.py`
- Delete: `src/menubar_macos.py`, `tools/audio_route.swift`, `tools/toggle.sh`, `tools/audio_route` (izlenmiyor), `.toggle_trigger` (izlenmiyor)
- Modify: `.gitignore` (`tools/audio_route` ve `.toggle_trigger` satırları Task 0'da kalktıysa dokunma)
- Test: `tests/test_status_text.py`, `tests/test_macos_system.py`

**Interfaces:**
- Consumes: `Controller`, `Phase`, `State`, `ErrorKind` (Task 6); `resolve`, `AppPaths`, `is_frozen` (Task 3); `setup_logging` (Task 3); `ModelManager` (Task 4); `get_capture_class` (mevcut); `src.__version__` (Task 0).
- Produces:
  - `src.ui.status_text.status_title(state: State, now: float) -> str`, `toggle_label(state: State) -> str` (Windows tepsi kabuğu da kullanacak)
  - `src.ui.macos_system`: `notification_command(title: str, body: str) -> list[str]`, `setup_notifications() -> None`, `notify(title: str, body: str) -> None`, `open_path(path: Path) -> None`, `open_url(url: str) -> None`, `login_item_supported() -> bool`, `login_item_enabled() -> bool`, `set_login_item(enabled: bool) -> bool`
  - `src.ui.menubar_macos.main() -> None` (PyInstaller giriş noktası Task 9'da bunu çağırır)

- [ ] **Step 1: Başarısız testleri yaz**

`tests/test_status_text.py`:

```python
from src.app.controller import ErrorKind, Phase, State
from src.ui.status_text import status_title, toggle_label


def test_titles():
    assert status_title(State(Phase.IDLE), 0) == "🎙"
    assert status_title(State(Phase.DOWNLOADING, progress=0.423), 0) == "⬇️ %42"
    assert status_title(State(Phase.TRANSCRIBING, progress=0.35), 0) == "⏳ %35"
    assert status_title(State(Phase.ERROR, error=ErrorKind.NETWORK), 0) == "⚠️"
    assert status_title(State(Phase.NEEDS_MODEL), 0) == "⚠️"


def test_recording_elapsed():
    assert status_title(State(Phase.RECORDING, started_at=100.0), 292.4) == "🔴 03:12"
    assert status_title(State(Phase.RECORDING, started_at=0.0), 3725.0) == "🔴 1:02:05"


def test_toggle_labels():
    assert toggle_label(State(Phase.IDLE)) == "Kaydı Başlat"
    assert toggle_label(State(Phase.RECORDING, started_at=0)) == "Kaydı Durdur"
    assert toggle_label(State(Phase.TRANSCRIBING, progress=0.1)) == "Transkript üretiliyor…"
    assert toggle_label(State(Phase.DOWNLOADING, progress=0.1)) == "Model indiriliyor…"
```

`tests/test_macos_system.py` (Review Focus 5):

```python
import subprocess
import sys

import pytest

from src.ui.macos_system import notification_command

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="yalnızca macOS")


def test_notification_command_escapes_quotes_and_turkish():
    cmd = notification_command('Transkript "hazır"', 'kayıt_ğüşiöç \\ "x".txt')
    assert cmd[:2] == ["osascript", "-e"]
    # AppleScript derlenebilir olmalı: bildirim göstermeden sözdizimini kontrol et
    script = cmd[2].replace("display notification", "return")
    script = script.split(" with title ")[0]
    out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == 'kayıt_ğüşiöç \\ "x".txt'
```

- [ ] **Step 2: Başarısız olduklarını gör**

Run: `.venv/bin/python -m pytest tests/test_status_text.py tests/test_macos_system.py -v`
Expected: FAIL (`ModuleNotFoundError: src.ui`).

- [ ] **Step 3: `src/ui/__init__.py` (boş) ve `src/ui/status_text.py` yaz**

```python
"""Controller durumunu kısa menü çubuğu / tepsi metinlerine çevirir (saf fonksiyonlar)."""

from __future__ import annotations

from src.app.controller import Phase, State


def _pct(progress: float | None) -> int:
    return int((progress or 0.0) * 100)


def status_title(state: State, now: float) -> str:
    phase = state.phase
    if phase is Phase.DOWNLOADING:
        return f"⬇️ %{_pct(state.progress)}"
    if phase is Phase.RECORDING:
        seconds = max(0, int(now - (state.started_at if state.started_at is not None else now)))
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        return f"🔴 {hours}:{minutes:02d}:{secs:02d}" if hours else f"🔴 {minutes:02d}:{secs:02d}"
    if phase is Phase.TRANSCRIBING:
        return f"⏳ %{_pct(state.progress)}"
    if phase in (Phase.ERROR, Phase.NEEDS_MODEL):
        return "⚠️"
    return "🎙"


def toggle_label(state: State) -> str:
    return {
        Phase.RECORDING: "Kaydı Durdur",
        Phase.TRANSCRIBING: "Transkript üretiliyor…",
        Phase.DOWNLOADING: "Model indiriliyor…",
    }.get(state.phase, "Kaydı Başlat")
```

- [ ] **Step 4: `src/ui/macos_system.py` yaz**

```python
"""macOS sistem entegrasyonları: bildirim, dosya/URL açma, oturum açılışında başlatma.

Paketli (imzalı) uygulamada UserNotifications ve SMAppService kullanılır;
kaynaktan çalışırken bunlar bundle gerektirdiği için bildirimler osascript ile
gösterilir ve oturum açılışında başlatma desteklenmez.
"""

from __future__ import annotations

import json
import logging
import subprocess
import uuid
from pathlib import Path

from src.app.paths import is_frozen

log = logging.getLogger(__name__)
_delegate = None  # UNUserNotificationCenter delegate'i zayıf referans tutar; burada canlı tut


def _applescript_string(text: str) -> str:
    # AppleScript string sözdizimi JSON ile aynı kaçışları (\" ve \\) kabul eder
    return json.dumps(text, ensure_ascii=False)


def notification_command(title: str, body: str) -> list[str]:
    script = f"display notification {_applescript_string(body)} with title {_applescript_string(title)}"
    return ["osascript", "-e", script]


def setup_notifications() -> None:
    """Bildirim izni ister ve uygulama öndeyken de banner gösterilmesini sağlar."""
    if not is_frozen():
        return
    global _delegate
    from Foundation import NSObject
    from UserNotifications import (
        UNAuthorizationOptionAlert,
        UNAuthorizationOptionSound,
        UNNotificationPresentationOptionBanner,
        UNNotificationPresentationOptionList,
        UNUserNotificationCenter,
    )

    class _Delegate(NSObject):
        def userNotificationCenter_willPresentNotification_withCompletionHandler_(self, center, notification, handler):
            handler(UNNotificationPresentationOptionBanner | UNNotificationPresentationOptionList)

    center = UNUserNotificationCenter.currentNotificationCenter()
    _delegate = _Delegate.alloc().init()
    center.setDelegate_(_delegate)
    center.requestAuthorizationWithOptions_completionHandler_(
        UNAuthorizationOptionAlert | UNAuthorizationOptionSound,
        lambda granted, error: log.info("Bildirim izni: %s %s", granted, error or ""),
    )


def notify(title: str, body: str) -> None:
    log.info("Bildirim: %s - %s", title, body)
    if not is_frozen():
        subprocess.run(notification_command(title, body), capture_output=True)
        return
    from UserNotifications import (
        UNMutableNotificationContent,
        UNNotificationRequest,
        UNUserNotificationCenter,
    )

    content = UNMutableNotificationContent.alloc().init()
    content.setTitle_(title)
    content.setBody_(body)
    request = UNNotificationRequest.requestWithIdentifier_content_trigger_(str(uuid.uuid4()), content, None)
    UNUserNotificationCenter.currentNotificationCenter().addNotificationRequest_withCompletionHandler_(
        request, lambda error: error and log.warning("Bildirim gösterilemedi: %s", error)
    )


def open_path(path: Path) -> None:
    subprocess.run(["open", str(path)])


def open_url(url: str) -> None:
    subprocess.run(["open", url])


def login_item_supported() -> bool:
    return is_frozen()


def login_item_enabled() -> bool:
    from ServiceManagement import SMAppService, SMAppServiceStatusEnabled

    return SMAppService.mainAppService().status() == SMAppServiceStatusEnabled


def set_login_item(enabled: bool) -> bool:
    from ServiceManagement import SMAppService

    service = SMAppService.mainAppService()
    ok, error = service.registerAndReturnError_(None) if enabled else service.unregisterAndReturnError_(None)
    if not ok:
        log.warning("Oturum açılışında başlatma ayarlanamadı (%s): %s", enabled, error)
    return bool(ok)
```

- [ ] **Step 5: Testleri çalıştır**

Run: `.venv/bin/python -m pytest tests/test_status_text.py tests/test_macos_system.py -v`
Expected: PASS.

- [ ] **Step 6: `src/ui/menubar_macos.py` yaz**

```python
"""macOS menü çubuğu uygulaması: Controller'ın ince gösterim kabuğu (rumps).

Çalıştırma (kaynaktan):  .venv/bin/python src/ui/menubar_macos.py
Paketli uygulamada giriş noktası packaging/entry_macos.py'dir.
"""

from __future__ import annotations

import logging
import queue
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import rumps  # noqa: E402

from src import __version__  # noqa: E402
from src.app.controller import Controller, Phase, State  # noqa: E402
from src.app.logging_setup import setup_logging  # noqa: E402
from src.app.model_manager import ModelManager  # noqa: E402
from src.app.paths import AppPaths, resolve  # noqa: E402
from src.audio.platform_detect import get_capture_class  # noqa: E402
from src.ui import macos_system  # noqa: E402
from src.ui.status_text import status_title, toggle_label  # noqa: E402

log = logging.getLogger(__name__)

_PERMISSION_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_AudioCapture"
_SILENCE_HINT = "Ses çalıyorduysa menüden 'Sistem Sesi İznini Aç…' ile izni kontrol et."
_LOGIN_MARKER = "login_item_initialized"


class _QueueListener:
    """Controller olaylarını (worker thread'lerinden) ana thread'e taşır."""

    def __init__(self) -> None:
        self.events: queue.Queue = queue.Queue()

    def on_state(self, state: State) -> None:
        self.events.put(("state", state))

    def on_message(self, title: str, body: str) -> None:
        self.events.put(("message", (title, body)))

    def on_transcript_ready(self, txt_path: Path) -> None:
        self.events.put(("ready", txt_path))


def _engine_factory(model_dir: Path):
    from src.transcribe.whisper_engine import WhisperEngine

    return WhisperEngine(model_size=str(model_dir), compute_type="int8_float32")


class TranscriptApp(rumps.App):
    def __init__(self, paths: AppPaths) -> None:
        super().__init__("Transkript", title="🎙", quit_button=None)
        self._paths = paths
        self._listener = _QueueListener()
        self._state = State(Phase.NEEDS_MODEL)
        self._controller = Controller(
            capture_factory=get_capture_class(),
            engine_factory=_engine_factory,
            model_manager=ModelManager(paths.models),
            output_dir=paths.output,
            listener=self._listener,
            silence_hint=_SILENCE_HINT,
        )

        self.toggle_item = rumps.MenuItem("Kaydı Başlat", callback=self._on_toggle)
        self.retry_item = rumps.MenuItem("Tekrar Dene")
        self.login_item = rumps.MenuItem("Oturum Açıldığında Başlat")
        self.menu = [
            self.toggle_item,
            self.retry_item,
            None,
            rumps.MenuItem("Son Transkripti Aç", callback=self._on_open_last),
            rumps.MenuItem("Transkript Klasörünü Aç", callback=lambda _: macos_system.open_path(paths.output)),
            None,
            self.login_item,
            rumps.MenuItem("Sistem Sesi İznini Aç…", callback=lambda _: macos_system.open_url(_PERMISSION_URL)),
            rumps.MenuItem("Hata Kaydını Göster", callback=lambda _: macos_system.open_path(paths.logs)),
            None,
            rumps.MenuItem(f"Transkript {__version__}"),
            rumps.MenuItem("Çıkış", callback=self._on_quit),
        ]
        self._init_login_item()
        macos_system.setup_notifications()
        rumps.Timer(self._on_tick, 0.25).start()
        self._controller.start()

    # --- oturum açılışında başlat ---

    def _init_login_item(self) -> None:
        if not macos_system.login_item_supported():
            self.login_item.title = "Oturum Açıldığında Başlat (yalnızca kurulu uygulamada)"
            return
        marker = self._paths.state / _LOGIN_MARKER
        if not marker.exists():  # ilk açılış: varsayılan olarak açık
            macos_system.set_login_item(True)
            marker.touch()
        self.login_item.state = int(macos_system.login_item_enabled())
        self.login_item.set_callback(self._on_login_item)

    def _on_login_item(self, sender) -> None:
        if macos_system.set_login_item(not sender.state):
            sender.state = int(macos_system.login_item_enabled())

    # --- menü olayları ---

    def _on_toggle(self, _sender) -> None:
        self._controller.toggle()

    def _on_retry(self, _sender) -> None:
        self._controller.retry_download()

    def _on_open_last(self, _sender) -> None:
        latest = self._controller.latest_transcript()
        if latest:
            macos_system.open_path(latest)
        else:
            macos_system.notify("Transkript yok", "Henüz üretilmiş bir transkript bulunamadı.")

    def _on_quit(self, _sender) -> None:
        if self._state.phase is Phase.TRANSCRIBING:
            answer = rumps.alert(
                title="Transkript sürüyor",
                message="Çıkarsan transkript yarıda kalır; ses kaydı klasörde durur. Yine de çıkılsın mı?",
                ok="Çık",
                cancel="Vazgeç",
            )
            if answer != 1:
                return
        self._controller.shutdown()
        rumps.quit_application()

    # --- ana thread döngüsü ---

    def _on_tick(self, _timer) -> None:
        while True:
            try:
                kind, payload = self._listener.events.get_nowait()
            except queue.Empty:
                break
            if kind == "state":
                self._apply_state(payload)
            elif kind == "message":
                macos_system.notify(*payload)
            elif kind == "ready":
                macos_system.notify("Transkript hazır", payload.name)
                macos_system.open_path(payload)
        self.title = status_title(self._state, time.monotonic())

    def _apply_state(self, state: State) -> None:
        self._state = state
        self.toggle_item.title = toggle_label(state)
        self.retry_item.set_callback(self._on_retry if state.phase is Phase.ERROR else None)


def main() -> None:
    paths = resolve().ensure()
    setup_logging(paths.logs)
    log.info("Transkript %s başlıyor (paketli: %s)", __version__, getattr(sys, "frozen", False))
    TranscriptApp(paths).run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Eski dosyaları kaldır**

Run:
```bash
git rm src/menubar_macos.py tools/audio_route.swift tools/toggle.sh
rm -f tools/audio_route .toggle_trigger
grep -rn "audio_route\|toggle_trigger\|toggle.sh\|BlackHole\|blackhole" src tests tools || echo "temiz"
```
Expected: `src/main.py` ve eski dosyalar dışında eşleşme yok (main.py Task 8'de düzelecek). Başka eşleşme varsa kaldır.

- [ ] **Step 8: Tüm testler**

Run: `.venv/bin/python -m pytest -q`
Expected: hepsi PASS.

- [ ] **Step 9: Kaynaktan elle uçtan uca test**

Önce varsa eski menü çubuğu sürecini kapat: `pkill -f menubar_macos.py || true`.
Run: `.venv/bin/python src/ui/menubar_macos.py`
Kontrol listesi (her birini gözle doğrula, görsel kusurları düzelt):
1. Menü çubuğunda `🎙` belirir (model `models/faster-whisper-medium`'da hazır olduğu için indirme yok).
2. Menü sırası: Kaydı Başlat · Tekrar Dene (gri) · ayraç · Son Transkripti Aç · Transkript Klasörünü Aç · ayraç · Oturum Açıldığında Başlat (yalnızca kurulu uygulamada, gri) · Sistem Sesi İznini Aç… · Hata Kaydını Göster · ayraç · Transkript 0.1.0 (gri) · Çıkış.
3. Bir YouTube videosu aç, "Kaydı Başlat" → `🔴 00:01` saymaya başlar, ses hoparlörden normal çıkar.
4. 30 sn sonra "Kaydı Durdur" → `⏳ %0` ... `⏳ %100` → "Transkript hazır" bildirimi, `.txt` TextEdit'te açılır, metin videoyla uyumlu.
5. Video oynatmadan kayıt al/durdur → "Kayıtta ses algılanmadı" bildirimi.
6. Transkript sürerken "Çıkış" → onay penceresi; "Vazgeç" uygulamayı açık tutar.
7. "Hata Kaydını Göster" → `logs/` açılır, `transkript.log` içinde kayıt satırları var.
8. Model indirme akışı: `mv models/faster-whisper-medium models/fwm.bak`, uygulamayı yeniden başlat → `⬇️ %..` ilerler. İndirme sürerken Wi-Fi'ı kapat → `⚠️` + "Model indirilemedi" bildirimi, "Tekrar Dene" etkin. Wi-Fi'ı aç, "Tekrar Dene" → indirme tamamlanır → "Hazır". Sonra iki kopyadan birini sil (`rm -rf models/fwm.bak`).

- [ ] **Step 10: Commit**

```bash
git add src/ui tests/test_status_text.py tests/test_macos_system.py
git commit -m "feat(macos): Controller tabanlı menü çubuğu uygulaması; BlackHole/audio_route/toggle kaldırıldı"
```

---

### Task 8: CLI ve dokümantasyon güncellemesi

**Files:**
- Modify: `src/main.py`
- Modify: `README.md`, `CLAUDE.md`, `AGENTS.md`

**Interfaces:**
- Consumes: `resolve()` (Task 3), `ModelManager` (Task 4), `CapturePermissionError` (Task 2).
- Produces: CLI `--model medium` için uygulamanın indirdiği düz model klasörünü kullanır; diğer model adları eskisi gibi HF önbelleğine iner.

- [ ] **Step 1: `src/main.py` değişiklikleri**

(a) Importların altına:
```python
from src.app.model_manager import ModelManager  # noqa: E402
from src.app.paths import resolve  # noqa: E402
```
(b) `--output-dir` varsayılanı: `default=str(resolve().output),` ve help `"Çıktı klasörü (varsayılan: output/)"` aynı kalsın.
(c) `_record_system_audio` içinde `capture = get_capture_class()()` ve `capture.start()` satırlarını izin hatasını yakalayacak şekilde değiştir:
```python
    from src.audio.platform_detect import CapturePermissionError, get_capture_class
    ...
    capture = get_capture_class()()
    try:
        capture.start()
    except CapturePermissionError:
        sys.exit(
            "Sistem sesi kaydı izni yok. Ayarlar > Gizlilik ve Güvenlik > "
            "Sistem Sesi Kaydı'ndan terminal uygulamana izin ver."
        )
    print(f"Ses kaynağı: {capture.device_hint()}")
    print("Kayıt başladı. Durdurmak için Ctrl+C'ye bas.\n")
```
(`print(f"Ses kaynağı...")` satırları `start()` sonrasına taşınır çünkü samplerate artık start'ta belirleniyor; eski `capture.start()` satırını sil.)
(d) Boş ses ve sessizlik mesajları:
```python
    if audio.size == 0:
        sys.exit("Hiç ses yakalanamadı.")
    ...
    if peak < 1e-4:
        print(
            "[uyarı] Kayıt tamamen sessiz görünüyor. macOS'ta Ayarlar > Gizlilik ve "
            "Güvenlik > Sistem Sesi Kaydı iznini kontrol et."
        )
```
(e) `main()` içinde motor oluşturma:
```python
    model = args.model
    if model == "medium":
        manager = ModelManager(resolve().models)
        if manager.is_ready():
            model = str(manager.model_dir)
    print(f"\nModel yükleniyor: {args.model} (ilk seferde indirilir, sonrası offline)")
    engine = WhisperEngine(model_size=model, compute_type=args.compute_type)
```

- [ ] **Step 2: CLI'yi dene**

Run: `.venv/bin/python src/main.py output/$(ls output | grep '\.wav$' | tail -1)`
Expected: Model `models/faster-whisper-medium`'dan yüklenir (indirme yok), transkript yazılır. Sonra eski HF önbelleğini sil: `rm -rf models/models--Systran--faster-whisper-medium` ve komutu tekrar çalıştır; yine indirme olmamalı.

- [ ] **Step 3: `README.md` güncelle**

- En üste "## Kurulum (son kullanıcı, macOS)" bölümü: "1. [Releases](https://github.com/bur4kceylann/meeting-transcripter/releases/latest) sayfasından `Transkript-x.y.z.dmg` indir. 2. Aç, Transkript'i Uygulamalar'a sürükle. 3. Transkript'i aç; menü çubuğunda model indirilir (~1.5 GB, bir kere). 4. 🎙 → Kaydı Başlat; ilk kayıtta 'sistem sesi' iznine İzin Ver. Gereksinim: Apple Silicon Mac, macOS 14.4+."
- "Gereksinimler" macOS satırı: `**macOS:** 14.4+ (Core Audio Process Tap; ek sürücü gerekmez)`.
- Geliştirici kurulumu: `pip install -r requirements-dev.txt`, Swift yardımcısı derleme komutu `swiftc -O -target arm64-apple-macos14.4 tools/audio_tap.swift -o tools/audio_tap`, menü çubuğu çalıştırma `.venv/bin/python src/ui/menubar_macos.py`, test komutları (`pytest`, `pytest -m e2e`), paketleme için `docs/release.md`'ye bağlantı.
- Kaldır: BlackHole, Multi-Output, `audio_route`, `toggle.sh` ve "Klavye Kısayolu Atama" bölümü.

- [ ] **Step 4: `CLAUDE.md` ve `AGENTS.md` güncelle (ikisinde aynı değişiklik)**

- "Hedef Platformlar" macOS satırı: `- **macOS** → Core Audio Process Tap (macOS 14.4+, sürücü gerekmez). tools/audio_tap (Swift) yardımcısı stdout'a PCM yazar, capture_macos.py okur.`
- "Teknoloji Yığını" ses satırı: `- Ses: **soundcard** (Windows loopback) + **sounddevice** (Linux) + **tools/audio_tap** (macOS)`
- Klasör yapısını güncelle: `src/app/` (controller, model_manager, paths, logging_setup), `src/ui/` (menubar_macos, macos_system, status_text), `tools/audio_tap.swift`, `packaging/`; `src/menubar_macos.py`, `tools/audio_route.swift`, `tools/toggle.sh` satırlarını sil.
- "Test / Doğrulama" bölümüne bir satır: `Birim testleri: pytest. Gerçek ses/model gerektirenler: pytest -m e2e. Dağıtım: docs/release.md.`

- [ ] **Step 5: Kalan BlackHole izi kalmadığını doğrula**

Run: `grep -rni "blackhole\|audio_route\|toggle.sh\|multi-output" --exclude-dir=.venv --exclude-dir=.git --exclude-dir=docs . || echo temiz`
Expected: `temiz`.

- [ ] **Step 6: Commit**

```bash
git add src/main.py README.md CLAUDE.md AGENTS.md
git commit -m "docs: macOS için Process Tap ve kurulabilir uygulama; CLI yeni model klasörünü kullanıyor"
```

---

### Task 9: Paketleme (ikon, PyInstaller, imzalama, DMG, notarization)

**Files:**
- Create: `packaging/make_icon.swift`, `packaging/Transkript.icns` (üretilen, commit edilir), `packaging/entry_macos.py`, `packaging/transkript.spec`, `packaging/entitlements.plist`, `packaging/build_macos.sh`

**Interfaces:**
- Consumes: `src.ui.menubar_macos.main()` (Task 7), `src.__version__` (Task 0), `WhisperEngine` (Task 5), `ModelManager` (Task 4).
- Produces: `bash packaging/build_macos.sh` → `dist/Transkript-<sürüm>.dmg` (imzalı, notarize, staple edilmiş). Ortam değişkenleri: `PYTHON`, `SIGN_IDENTITY`, `NOTARY_PROFILE` veya `NOTARY_KEY_PATH`+`NOTARY_KEY_ID`+`NOTARY_ISSUER`, `SKIP_NOTARIZE=1`, `SELF_TEST_MODEL=<model klasörü>`. Paketli uygulama `--self-test <model_dir> <ses_dosyası>` argümanlarıyla transkripti stdout'a yazıp çıkar.

- [ ] **Step 1: İkon üretici `packaging/make_icon.swift`**

```swift
// Transkript uygulama ikonunu üretir (1024x1024 PNG).
// Kullanım: swift packaging/make_icon.swift build/icon_1024.png
import AppKit

let canvas: CGFloat = 1024
let image = NSImage(size: NSSize(width: canvas, height: canvas))
image.lockFocus()

// macOS ikon ızgarası: 824 pt içerik, köşe yarıçapı ~185
let body = NSRect(x: 100, y: 100, width: 824, height: 824)
let path = NSBezierPath(roundedRect: body, xRadius: 185, yRadius: 185)
let shadow = NSShadow()
shadow.shadowColor = NSColor.black.withAlphaComponent(0.25)
shadow.shadowOffset = NSSize(width: 0, height: -12)
shadow.shadowBlurRadius = 28
NSGraphicsContext.saveGraphicsState()
shadow.set()
NSColor.white.setFill()
path.fill()
NSGraphicsContext.restoreGraphicsState()

NSGradient(
    starting: NSColor(calibratedRed: 1.00, green: 0.42, blue: 0.36, alpha: 1),
    ending: NSColor(calibratedRed: 0.86, green: 0.15, blue: 0.33, alpha: 1)
)!.draw(in: path, angle: -90)

let config = NSImage.SymbolConfiguration(pointSize: 430, weight: .semibold)
    .applying(NSImage.SymbolConfiguration(paletteColors: [.white]))
let symbol = NSImage(systemSymbolName: "waveform", accessibilityDescription: nil)!
    .withSymbolConfiguration(config)!
let size = symbol.size
symbol.draw(in: NSRect(x: (canvas - size.width) / 2, y: (canvas - size.height) / 2,
                       width: size.width, height: size.height))
image.unlockFocus()

let rep = NSBitmapImageRep(data: image.tiffRepresentation!)!
try! rep.representation(using: .png, properties: [:])!
    .write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
```

- [ ] **Step 2: `.icns` üret ve gözle kontrol et**

Run:
```bash
mkdir -p build/Transkript.iconset
swift packaging/make_icon.swift build/icon_1024.png
for s in 16 32 128 256 512; do
  sips -z $s $s build/icon_1024.png --out build/Transkript.iconset/icon_${s}x${s}.png >/dev/null
  sips -z $((s*2)) $((s*2)) build/icon_1024.png --out build/Transkript.iconset/icon_${s}x${s}@2x.png >/dev/null
done
iconutil -c icns build/Transkript.iconset -o packaging/Transkript.icns
open build/icon_1024.png
```
Expected: Kırmızı-pembe gradyanlı yuvarlatılmış kare üzerinde ortalanmış beyaz dalga formu. Ortalanmamış, kenara taşan veya bulanık bir şey varsa düzelt. Ayrıca Finder'da `packaging/Transkript.icns`'i seçip boşluk tuşuyla küçük boyutta net olduğunu kontrol et.

- [ ] **Step 3: Giriş noktası `packaging/entry_macos.py`**

```python
"""PyInstaller giriş noktası (Transkript.app).

`--self-test <model_dir> <ses_dosyası>`: paketin tüm ağır bağımlılıklarının
(ctranslate2, onnxruntime VAD, PyAV) imzalı paket içinde yüklenebildiğini
doğrulamak için transkripti stdout'a yazar ve çıkar. Derleme betiği kullanır.
"""

import sys


def _self_test(model_dir: str, audio_path: str) -> None:
    from src.transcribe.whisper_engine import WhisperEngine

    result = WhisperEngine(model_size=model_dir).transcribe(audio_path)
    print(result.text)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--self-test":
        _self_test(sys.argv[2], sys.argv[3])
        sys.exit(0)
    from src.ui.menubar_macos import main

    main()
```

- [ ] **Step 4: Entitlements `packaging/entitlements.plist`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.device.audio-input</key>
    <true/>
</dict>
</plist>
```

- [ ] **Step 5: PyInstaller spec `packaging/transkript.spec`**

```python
# PyInstaller spec: macOS Transkript.app (arm64, onedir)
# Kullanım: packaging/build_macos.sh (doğrudan çağırma)
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from src import __version__  # noqa: E402

a = Analysis(
    [str(ROOT / "packaging" / "entry_macos.py")],
    pathex=[str(ROOT)],
    binaries=[(str(ROOT / "build" / "audio_tap"), ".")] + collect_dynamic_libs("ctranslate2"),
    datas=collect_data_files("faster_whisper"),
    hiddenimports=["src.audio.capture_macos"],
    excludes=["sounddevice", "soundcard", "tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Transkript",
    console=False,
    target_arch="arm64",
)
coll = COLLECT(exe, a.binaries, a.datas, name="Transkript")
app = BUNDLE(
    coll,
    name="Transkript.app",
    icon=str(ROOT / "packaging" / "Transkript.icns"),
    bundle_identifier="com.burakceylan.transkript",
    version=__version__,
    info_plist={
        "CFBundleName": "Transkript",
        "CFBundleDisplayName": "Transkript",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "LSUIElement": True,
        "LSMinimumSystemVersion": "14.4",
        "NSAudioCaptureUsageDescription": "Toplantı ve videolardaki sesi metne çevirmek için sistem sesini kaydeder.",
        "NSDocumentsFolderUsageDescription": "Transkriptleri Belgeler > Transkriptler klasörüne kaydetmek için.",
        "NSHumanReadableCopyright": "© 2026 Burak Ceylan",
    },
)
```

- [ ] **Step 6: Derleme betiği `packaging/build_macos.sh`**

```bash
#!/bin/bash
# Transkript.app'i derler, imzalar, .dmg'ye koyar ve notarize eder.
# Yerelde ve CI'da aynı betik çalışır. Ayrıntılar: docs/release.md
#
# Ortam değişkenleri:
#   PYTHON           Python yorumlayıcısı (varsayılan: .venv/bin/python)
#   SIGN_IDENTITY    imza kimliği (varsayılan: Developer ID Application: BURAK CEYLAN (4F8TVA268Y))
#   NOTARY_PROFILE   yerelde notarytool keychain profili (varsayılan: transkript-notary)
#   NOTARY_KEY_PATH, NOTARY_KEY_ID, NOTARY_ISSUER   CI'da App Store Connect API anahtarı
#   SKIP_NOTARIZE=1  notarization'ı atla (hızlı yerel deneme)
#   SELF_TEST_MODEL  model klasörü verilirse imzalı paketle transkript self-test'i yapılır
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-.venv/bin/python}"
IDENTITY="${SIGN_IDENTITY:-Developer ID Application: BURAK CEYLAN (4F8TVA268Y)}"
ENTITLEMENTS="packaging/entitlements.plist"
VERSION="$("$PY" -c 'from src import __version__; print(__version__)')"
APP="dist/Transkript.app"
DMG="dist/Transkript-$VERSION.dmg"

echo "==> audio_tap derleniyor"
mkdir -p build
swiftc -O -target arm64-apple-macos14.4 tools/audio_tap.swift -o build/audio_tap

echo "==> PyInstaller ($VERSION)"
rm -rf "$APP" dist/Transkript
"$PY" -m PyInstaller --noconfirm --clean --distpath dist --workpath build/pyinstaller packaging/transkript.spec

echo "==> İmzalama"
sign() {
  codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$1"
}
# İçten dışa: önce tüm Mach-O dosyaları, sonra iç .framework paketleri, en son .app
while IFS= read -r -d '' f; do
  if file -b "$f" | grep -q "Mach-O"; then sign "$f"; fi
done < <(find "$APP/Contents" -type f -print0)
while IFS= read -r -d '' fw; do sign "$fw"; done < <(find "$APP/Contents" -type d -name "*.framework" -print0 | sort -rz)
sign "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

if [[ -n "${SELF_TEST_MODEL:-}" ]]; then
  echo "==> Self-test (imzalı paket, hardened runtime)"
  say -o build/selftest.aiff "Hello, this is a packaging test."
  "$APP/Contents/MacOS/Transkript" --self-test "$SELF_TEST_MODEL" build/selftest.aiff | tee build/selftest.txt
  grep -qi "test" build/selftest.txt
fi

echo "==> DMG"
STAGE="build/dmg"
rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
ditto "$APP" "$STAGE/Transkript.app"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Transkript" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
codesign --force --timestamp --sign "$IDENTITY" "$DMG"

if [[ "${SKIP_NOTARIZE:-0}" != "1" ]]; then
  echo "==> Notarization"
  if [[ -n "${NOTARY_KEY_PATH:-}" ]]; then
    AUTH=(--key "$NOTARY_KEY_PATH" --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER")
  else
    AUTH=(--keychain-profile "${NOTARY_PROFILE:-transkript-notary}")
  fi
  xcrun notarytool submit "$DMG" "${AUTH[@]}" --wait --output-format json | tee build/notary.json
  STATUS="$("$PY" -c 'import json; print(json.load(open("build/notary.json"))["status"])')"
  if [[ "$STATUS" != "Accepted" ]]; then
    ID="$("$PY" -c 'import json; print(json.load(open("build/notary.json"))["id"])')"
    xcrun notarytool log "$ID" "${AUTH[@]}"
    echo "Notarization başarısız: $STATUS" >&2
    exit 1
  fi
  xcrun stapler staple "$DMG"
  xcrun stapler validate "$DMG"
  spctl -a -vv -t open --context context:primary-signature "$DMG"
fi

echo "==> Hazır: $DMG"
```

Run: `chmod +x packaging/build_macos.sh`

- [ ] **Step 7: İmzalı ama notarize edilmemiş derleme + self-test**

Run: `SKIP_NOTARIZE=1 SELF_TEST_MODEL=build/models/faster-whisper-tiny bash packaging/build_macos.sh`
(`build/models/faster-whisper-tiny` Task 4 Step 5'te indirildi; yoksa o adımı tekrarla.)
Expected: `codesign --verify` geçer, self-test çıktısında "test" kelimesi geçer.
Hata durumları ve çözümleri:
  - Self-test `ModuleNotFoundError`/eksik dosya (ör. `silero_vad*.onnx`, `av`, `onnxruntime`): spec'teki `datas`/`binaries`'e `collect_data_files("<paket>")` / `collect_dynamic_libs("<paket>")` ekle ve tekrar derle.
  - Self-test hardened runtime nedeniyle çöküyor (`Killed: 9`, crash raporunda "CODE SIGNING" veya "executable memory"): `entitlements.plist`'e `<key>com.apple.security.cs.allow-unsigned-executable-memory</key><true/>` ekle, tekrar derle; bunun neden gerektiğini plist'te yorum olarak yaz.
  - `codesign --verify` iç bileşen imzasız diyorsa: o dosya türünü (`file -b` çıktısı) imza döngüsüne dahil et.

- [ ] **Step 8: Notarization profili (bir kerelik, kullanıcıyla) ve tam derleme**

Kullanıcıdan App Store Connect API anahtarını iste (`docs/release.md` Task 10'da yazılıyor; şimdilik adımlar: App Store Connect → Users and Access → Integrations → Team Keys → "+" → Access: Developer → `.p8` indir, Key ID ve Issuer ID'yi not et).
Run:
```bash
xcrun notarytool store-credentials transkript-notary --key ~/Downloads/AuthKey_<KEYID>.p8 --key-id <KEYID> --issuer <ISSUER>
SELF_TEST_MODEL=build/models/faster-whisper-tiny bash packaging/build_macos.sh
```
Expected: `status: Accepted`, `stapler validate` "The validate action worked!", `spctl` "accepted ... source=Notarized Developer ID". Çıktı: `dist/Transkript-0.1.0.dmg`.

- [ ] **Step 9: DMG görünümünü kontrol et**

Run: `open dist/Transkript-0.1.0.dmg`
Expected: Finder penceresinde Transkript ikonu ve Applications kısayolu görünür; ikon net. Pencere düzeni dağınıksa (ikonlar üst üste / çok küçük pencere) sorun olarak not et ve `create-dmg` benzeri bir düzen adımı eklemeyi Task 11 bulgularına yaz.

- [ ] **Step 10: Commit**

```bash
git add packaging/make_icon.swift packaging/Transkript.icns packaging/entry_macos.py packaging/transkript.spec packaging/entitlements.plist packaging/build_macos.sh
git commit -m "build(macos): PyInstaller paketi, imzalama, DMG ve notarization betiği"
```

---

### Task 10: GitHub Actions ve sürüm süreci dokümantasyonu

**Files:**
- Create: `.github/workflows/test.yml`, `.github/workflows/release.yml`, `packaging/release-notes.md`, `docs/release.md`

**Interfaces:**
- Consumes: `packaging/build_macos.sh` (Task 9), `ModelManager` (Task 4).
- Produces: push/PR'da test; `v*` etiketinde imzalı/notarize `.dmg`'li GitHub Release. Gerekli secrets: `MACOS_CERT_P12`, `MACOS_CERT_PASSWORD`, `NOTARY_KEY_P8`, `NOTARY_KEY_ID`, `NOTARY_ISSUER`.

- [ ] **Step 1: `.github/workflows/test.yml`**

```yaml
name: test

on:
  push:
    branches: [main]
  pull_request:

jobs:
  macos:
    runs-on: macos-15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -r requirements-dev.txt
      - name: audio_tap derlenebiliyor mu
        run: swiftc -O -target arm64-apple-macos14.4 tools/audio_tap.swift -o tools/audio_tap
      - run: pytest
```

- [ ] **Step 2: `.github/workflows/release.yml`**

```yaml
name: release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  macos:
    runs-on: macos-15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -r requirements-dev.txt

      - name: Etiket sürüm numarasıyla eşleşiyor mu
        run: test "v$(python -c 'from src import __version__; print(__version__)')" = "$GITHUB_REF_NAME"

      - run: pytest

      - name: İmza sertifikasını geçici keychain'e al
        env:
          MACOS_CERT_P12: ${{ secrets.MACOS_CERT_P12 }}
          MACOS_CERT_PASSWORD: ${{ secrets.MACOS_CERT_PASSWORD }}
        run: |
          KEYCHAIN="$RUNNER_TEMP/build.keychain-db"
          KEYCHAIN_PASSWORD="$(uuidgen)"
          echo "$MACOS_CERT_P12" | base64 --decode > "$RUNNER_TEMP/cert.p12"
          security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
          security set-keychain-settings -lut 21600 "$KEYCHAIN"
          security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
          security import "$RUNNER_TEMP/cert.p12" -P "$MACOS_CERT_PASSWORD" -A -t cert -f pkcs12 -k "$KEYCHAIN"
          security set-key-partition-list -S apple-tool:,apple: -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
          security list-keychains -d user -s "$KEYCHAIN" $(security list-keychains -d user | tr -d '"')
          rm "$RUNNER_TEMP/cert.p12"

      - name: Notarization anahtarı
        env:
          NOTARY_KEY_P8: ${{ secrets.NOTARY_KEY_P8 }}
        run: echo "$NOTARY_KEY_P8" > "$RUNNER_TEMP/notary.p8"

      - name: Self-test modeli (tiny)
        run: |
          python -c "
          from pathlib import Path
          from src.app.model_manager import ModelManager
          m = ModelManager(Path('build/models'), repo='Systran/faster-whisper-tiny')
          m.download(lambda p: None)
          print(m.model_dir)
          "

      - name: Derle, imzala, notarize et
        env:
          PYTHON: python
          NOTARY_KEY_PATH: ${{ runner.temp }}/notary.p8
          NOTARY_KEY_ID: ${{ secrets.NOTARY_KEY_ID }}
          NOTARY_ISSUER: ${{ secrets.NOTARY_ISSUER }}
          SELF_TEST_MODEL: build/models/faster-whisper-tiny
        run: bash packaging/build_macos.sh

      - name: GitHub Release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release create "$GITHUB_REF_NAME" dist/Transkript-*.dmg \
            --title "Transkript $GITHUB_REF_NAME" \
            --notes-file packaging/release-notes.md
```

- [ ] **Step 3: `packaging/release-notes.md`** (Release sayfasında müdürün göreceği metin)

```markdown
## Kurulum (Mac)

1. Aşağıdaki **Assets** bölümünden `Transkript-….dmg` dosyasını indir ve çift tıkla.
2. Açılan pencerede **Transkript** simgesini **Applications** klasörüne sürükle.
3. Uygulamalar'dan **Transkript**'i aç. Ekranın üstündeki menü çubuğunda bir simge belirir
   ve model bir kereliğine indirilir (yaklaşık 1.5 GB, birkaç dakika).
4. "Hazır" bildirimi gelince 🎙 simgesine tıkla → **Kaydı Başlat**.
   İlk kayıtta Mac "sistem sesi kaydı" izni sorar: **İzin Ver**.

## Kullanım

- 🎙 → **Kaydı Başlat**: toplantı veya video sesi kaydedilir (🔴 süre görünür).
- 🎙 → **Kaydı Durdur**: metin hazırlanır (⏳ yüzde görünür), bitince dosya kendiliğinden açılır.
- Tüm transkriptler **Belgeler > Transkriptler** klasöründe.

Gereksinim: Apple Silicon (M1 ve sonrası) Mac, macOS 14.4 veya daha yeni.
Bir sorun olursa menüden **Hata Kaydını Göster**'e tıklayıp açılan klasördeki dosyayı gönder.
```

- [ ] **Step 4: `docs/release.md`** (geliştirici için sürüm süreci)

```markdown
# Sürüm Çıkarma (macOS)

## Bir kerelik kurulum

### 1. İmza sertifikası (GitHub Secrets)
1. Anahtar Zinciri Erişimi → "Developer ID Application: BURAK CEYLAN (4F8TVA268Y)"
   sertifikasını (özel anahtarıyla birlikte) sağ tık → Dışa Aktar → `cert.p12`, bir parola belirle.
2. Secrets'a ekle:
   ```bash
   base64 -i cert.p12 | gh secret set MACOS_CERT_P12
   gh secret set MACOS_CERT_PASSWORD   # parolayı yapıştır
   rm cert.p12
   ```

### 2. Notarization API anahtarı
1. App Store Connect → Users and Access → Integrations → Team Keys → "+",
   Access: **Developer**. `AuthKey_<KEYID>.p8` dosyasını indir (bir kez indirilebilir).
2. Secrets'a ekle:
   ```bash
   gh secret set NOTARY_KEY_P8 < AuthKey_<KEYID>.p8
   gh secret set NOTARY_KEY_ID      # Key ID
   gh secret set NOTARY_ISSUER      # Issuer ID (sayfanın üstünde)
   ```
3. Yerelde derleme için keychain profili:
   ```bash
   xcrun notarytool store-credentials transkript-notary \
     --key AuthKey_<KEYID>.p8 --key-id <KEYID> --issuer <ISSUER>
   ```

## Her sürümde
1. `src/__init__.py` içindeki `__version__`'ı artır (ör. `0.1.1`), commit + push.
2. Etiketle: `git tag v0.1.1 && git push origin v0.1.1`
3. Actions'taki `release` işini izle: `gh run watch`
4. Release sayfasındaki `.dmg`'yi indirip doğrula:
   `spctl -a -vv -t open --context context:primary-signature Transkript-0.1.1.dmg`
5. Kullanıcıya Release linkini gönder; güncelleme = yeni `.dmg`'yi indirip uygulamayı üstüne sürüklemek.

## Yerelde derleme
`bash packaging/build_macos.sh` (hızlı deneme: `SKIP_NOTARIZE=1`). Değişkenler betiğin başında.
```

- [ ] **Step 5: Secrets'ları kullanıcıyla ekle ve test iş akışını doğrula**

Kullanıcıyla `docs/release.md` "Bir kerelik kurulum" adımlarını birlikte yap (sertifika dışa aktarma ve parola kullanıcının elinde). Sonra:
Run: `git add .github packaging/release-notes.md docs/release.md && git commit -m "ci: test ve imzalı/notarize macOS release iş akışları" && git push origin main && gh run watch`
Expected: `test` iş akışı yeşil.

---

### Task 11: Paketli uygulama uçtan uca testi ve v0.1.0 sürümü

**Files:**
- Değişiklik yalnızca bulunan hatalar için (her düzeltme kendi commit'iyle, gerekiyorsa test ekleyerek).

- [ ] **Step 1: Temiz kullanıcı hesabı hazırla.** Kullanıcıdan Ayarlar → Kullanıcılar ve Gruplar'dan "Transkript Test" adlı standart bir hesap açmasını iste (müdürün ilk deneyimini taklit eder: model yok, izin yok, oturum açılış öğesi yok). `dist/Transkript-0.1.0.dmg`'yi `/Users/Shared/`'a kopyala.

- [ ] **Step 2: Test hesabında kontrol listesi** (her maddeyi ekran görüntüsüyle doğrula; görsel kusurları da hata say):
1. DMG açılır, sürükle-bırak çalışır, ilk açılışta Gatekeeper yalnızca "internetten indirildi, açılsın mı?" sorar (geliştirici uyarısı yok).
2. Bildirim izni sorulur; menü çubuğunda `⬇️ %..` ilerler, bitince "Hazır" bildirimi gelir.
3. Belgeler klasörü erişim izni penceresi çıkarsa metni Türkçe ve anlaşılır (`NSDocumentsFolderUsageDescription`).
4. İlk kayıtta "sistem sesi kaydı" izin penceresi Transkript adıyla ve Türkçe açıklamayla çıkar. (Yardımcı yerine uygulamaya atfedildiğini doğrula; atfedilmiyorsa spec'teki yedek plana geç ve kullanıcıya bildir.)
5. YouTube'da Türkçe bir video: kayıt → durdur → `⏳ %` → `.txt` açılır, `~/Documents/Transkriptler`'de `.wav/.txt/.srt` var.
6. Kayıt sırasında AirPods/kulaklık bağla veya çıkar (Review Focus 2): kayıt bozulmadan biter, o ana kadarki ses transkriptte var.
7. İzni reddetme yolu: Ayarlar'dan Transkript'in sistem sesi iznini kapat → kayıt dene → izin bildirimi veya "ses algılanmadı + izin ipucu"; "Sistem Sesi İznini Aç…" doğru Ayarlar sayfasını açar.
8. "Oturum Açıldığında Başlat" işaretli; oturumu kapatıp açınca uygulama menü çubuğunda.
9. Model indirirken Wi-Fi kesme → `⚠️` + "Tekrar Dene" çalışır.
10. Transkript sırasında Çıkış → onay penceresi.
11. 1 saatlik bir kayıt (uzun bir video): bellek Etkinlik Monitörü'nde makul (< 2 GB), transkript tamamlanır (Review Focus 1).

- [ ] **Step 3: Bulunan hataları düzelt.** Her biri için önce kullanıcı gibi tekrar üret, sonra düzelt, ilgili birim testi ekle, `pytest` geçsin, yeniden derle ve maddeyi tekrar doğrula. Commit: `fix(...): ...`.

- [ ] **Step 4: v0.1.0'ı yayınla**

Run:
```bash
git push origin main
git tag v0.1.0 && git push origin v0.1.0
gh run watch
gh release view v0.1.0
```
Expected: Release'te `Transkript-0.1.0.dmg` ve Türkçe kurulum notları. İndirip doğrula: `gh release download v0.1.0 -D build/release && spctl -a -vv -t open --context context:primary-signature build/release/Transkript-0.1.0.dmg` → "accepted, source=Notarized Developer ID".

- [ ] **Step 5: Kullanıcıya teslim.** Release linkini (`https://github.com/bur4kceylann/meeting-transcripter/releases/latest`) ve release notlarındaki 4 adımı müdüre gönderilmek üzere kullanıcıya ver. Test hesabının silinebileceğini hatırlat.
