// Ses çıkışı yönlendirme yardımcısı (macOS).
//
//   audio_route current      → mevcut varsayılan çıkışın UID ve adını yazar
//   audio_route ensure       → "Hoparlör + BlackHole" Multi-Output Device'ı
//                              (yoksa oluşturup) varsayılan çıkış yapar;
//                              ÖNCEKİ cihazın UID'sini stdout'a yazar
//   audio_route set <uid>    → verilen UID'li cihazı varsayılan çıkış yapar
//
// Derleme: swiftc -O tools/audio_route.swift -o tools/audio_route
import CoreAudio
import Foundation

let systemObj = AudioObjectID(kAudioObjectSystemObject)
let aggregateUIDPrefix = "com.burak-transcripter.multi-output."

func sanitize(_ s: String) -> String {
    String(s.map { $0.isLetter || $0.isNumber ? $0 : "-" })
}

// Fiziksel çıkış cihazına özel, kararlı bir aggregate UID üretir; böylece
// hoparlör ve AirPods gibi farklı cihazlar için ayrı ayrı (ve doğru) multi-output
// cihazları tutulur, biri diğerinin yerine yanlışlıkla kullanılmaz.
func derivedAggregateUID(for physicalUID: String) -> String {
    aggregateUIDPrefix + sanitize(physicalUID)
}

func propertyAddress(_ selector: AudioObjectPropertySelector) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(
        mSelector: selector,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain)
}

func getString(_ device: AudioObjectID, _ selector: AudioObjectPropertySelector) -> String? {
    var addr = propertyAddress(selector)
    guard AudioObjectHasProperty(device, &addr) else { return nil }
    var value: Unmanaged<CFString>?
    var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    let err = AudioObjectGetPropertyData(device, &addr, 0, nil, &size, &value)
    guard err == noErr, let cf = value?.takeRetainedValue() else { return nil }
    return cf as String
}

func allDevices() -> [AudioObjectID] {
    var addr = propertyAddress(kAudioHardwarePropertyDevices)
    var size: UInt32 = 0
    guard AudioObjectGetPropertyDataSize(systemObj, &addr, 0, nil, &size) == noErr else { return [] }
    var devices = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
    guard AudioObjectGetPropertyData(systemObj, &addr, 0, nil, &size, &devices) == noErr else { return [] }
    return devices
}

func findByUID(_ uid: String) -> AudioObjectID? {
    allDevices().first { getString($0, kAudioDevicePropertyDeviceUID) == uid }
}

func defaultOutputDevice() -> AudioObjectID {
    var addr = propertyAddress(kAudioHardwarePropertyDefaultOutputDevice)
    var device = AudioObjectID(0)
    var size = UInt32(MemoryLayout<AudioObjectID>.size)
    AudioObjectGetPropertyData(systemObj, &addr, 0, nil, &size, &device)
    return device
}

func setDefaultOutput(_ device: AudioObjectID) -> Bool {
    var addr = propertyAddress(kAudioHardwarePropertyDefaultOutputDevice)
    var dev = device
    return AudioObjectSetPropertyData(systemObj, &addr, 0, nil,
        UInt32(MemoryLayout<AudioObjectID>.size), &dev) == noErr
}

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(1)
}

let args = CommandLine.arguments
guard args.count >= 2 else { fail("kullanım: audio_route current|ensure|set <uid>") }

switch args[1] {
case "current":
    let dev = defaultOutputDevice()
    let uid = getString(dev, kAudioDevicePropertyDeviceUID) ?? "?"
    let name = getString(dev, kAudioObjectPropertyName as AudioObjectPropertySelector) ?? "?"
    print("\(uid)\t\(name)")

case "set":
    guard args.count >= 3 else { fail("kullanım: audio_route set <uid>") }
    guard let dev = findByUID(args[2]) else { fail("cihaz bulunamadı: \(args[2])") }
    guard setDefaultOutput(dev) else { fail("varsayılan çıkış ayarlanamadı") }
    print("OK")

case "ensure":
    let previous = defaultOutputDevice()
    let previousUID = getString(previous, kAudioDevicePropertyDeviceUID) ?? ""

    if previousUID.hasPrefix(aggregateUIDPrefix) {
        print(previousUID)  // zaten bu aracın oluşturduğu bir multi-output'tayız
        exit(0)
    }
    let aggregateUID = derivedAggregateUID(for: previousUID)
    if let existing = findByUID(aggregateUID) {
        guard setDefaultOutput(existing) else { fail("varsayılan çıkış ayarlanamadı") }
        print(previousUID)
        exit(0)
    }

    // BlackHole'u bul
    var blackholeUID: String? = nil
    for dev in allDevices() {
        if let name = getString(dev, kAudioObjectPropertyName as AudioObjectPropertySelector),
           name.lowercased().contains("blackhole"),
           let uid = getString(dev, kAudioDevicePropertyDeviceUID) {
            blackholeUID = uid
            break
        }
    }
    guard let bhUID = blackholeUID else { fail("BlackHole cihazı bulunamadı (kurulu mu?)") }
    guard !previousUID.isEmpty, !previousUID.lowercased().contains("blackhole") else {
        fail("mevcut çıkış cihazı belirlenemedi")
    }

    let previousName = getString(previous, kAudioObjectPropertyName as AudioObjectPropertySelector) ?? "Çıkış"
    let description: [String: Any] = [
        kAudioAggregateDeviceNameKey: "\(previousName) + BlackHole",
        kAudioAggregateDeviceUIDKey: aggregateUID,
        kAudioAggregateDeviceIsStackedKey: 1,  // "stacked" = Multi-Output Device
        kAudioAggregateDeviceSubDeviceListKey: [
            [kAudioSubDeviceUIDKey: previousUID],  // ilk cihaz saat kaynağı
            [kAudioSubDeviceUIDKey: bhUID, kAudioSubDeviceDriftCompensationKey: 1],
        ],
    ]
    var aggregateID = AudioObjectID(0)
    guard AudioHardwareCreateAggregateDevice(description as CFDictionary, &aggregateID) == noErr else {
        fail("multi-output device oluşturulamadı")
    }
    guard setDefaultOutput(aggregateID) else { fail("varsayılan çıkış ayarlanamadı") }
    print(previousUID)

default:
    fail("bilinmeyen komut: \(args[1])")
}
