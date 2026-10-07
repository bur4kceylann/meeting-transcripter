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
    return withUnsafeMutablePointer(to: &value) {
        AudioObjectGetPropertyData(object, &address, 0, nil, &size, $0)
    }
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
