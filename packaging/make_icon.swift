// Transkript uygulama ikonunu üretir (1024x1024 PNG).
// Kullanım: swift packaging/make_icon.swift build/icon_1024.png
import AppKit

let canvas = 1024

func draw(into rep: NSBitmapImageRep, _ body: () -> Void) {
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    body()
    NSGraphicsContext.restoreGraphicsState()
}

func makeBitmap(_ width: Int, _ height: Int) -> NSBitmapImageRep {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
                               bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                               colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    // Yeni bitmap'in içeriği sıfırlanmış garanti değil: açıkça şeffaf yap
    draw(into: rep) {
        NSColor.clear.set()
        NSRect(x: 0, y: 0, width: width, height: height).fill(using: .copy)
    }
    return rep
}

/// Görünen (alfa > 0) piksellerin sınırları; AppKit koordinatlarında (alt-sol başlangıç).
func opaqueBounds(_ rep: NSBitmapImageRep, where keep: (NSColor) -> Bool) -> NSRect {
    var minX = rep.pixelsWide, minY = rep.pixelsHigh, maxX = -1, maxY = -1
    for y in 0..<rep.pixelsHigh {
        for x in 0..<rep.pixelsWide where keep(rep.colorAt(x: x, y: y)!) {
            minX = min(minX, x); maxX = max(maxX, x)
            minY = min(minY, y); maxY = max(maxY, y)
        }
    }
    // colorAt'te y yukarıdan aşağı; AppKit çizimi aşağıdan yukarı
    return NSRect(x: minX, y: rep.pixelsHigh - 1 - maxY, width: maxX - minX + 1, height: maxY - minY + 1)
}

// 1) SF Symbol'ü ayrı bir bitmap'e çiz ve görünen sınırlarını ölç
let config = NSImage.SymbolConfiguration(pointSize: 430, weight: .semibold)
    .applying(NSImage.SymbolConfiguration(paletteColors: [.white]))
let symbol = NSImage(systemSymbolName: "waveform", accessibilityDescription: nil)!
    .withSymbolConfiguration(config)!
let symbolRep = makeBitmap(Int(symbol.size.width.rounded(.up)), Int(symbol.size.height.rounded(.up)))
let symbolRect = NSRect(origin: .zero, size: symbol.size)
draw(into: symbolRep) { symbol.draw(in: symbolRect) }
let ink = opaqueBounds(symbolRep) { $0.alphaComponent > 0.01 }

// 2) İkon: macOS ızgarası (824 pt içerik, köşe yarıçapı ~185), gölge, gradyan
let rep = makeBitmap(canvas, canvas)
let body = NSRect(x: 100, y: 100, width: 824, height: 824)
draw(into: rep) {
    let path = NSBezierPath(roundedRect: body, xRadius: 185, yRadius: 185)
    NSGraphicsContext.saveGraphicsState()
    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.28)
    shadow.shadowOffset = NSSize(width: 0, height: -10)
    shadow.shadowBlurRadius = 24
    shadow.set()
    NSColor.white.setFill()
    path.fill()
    NSGraphicsContext.restoreGraphicsState()

    NSGradient(
        starting: NSColor(srgbRed: 0.98, green: 0.36, blue: 0.30, alpha: 1),
        ending: NSColor(srgbRed: 0.80, green: 0.10, blue: 0.30, alpha: 1)
    )!.draw(in: path, angle: -90)

    // Görünen mürekkebin merkezi ikon gövdesinin merkezine gelsin
    let origin = NSPoint(x: body.midX - ink.midX, y: body.midY - ink.midY)
    symbol.draw(in: symbolRect.offsetBy(dx: origin.x, dy: origin.y))
}

// 3) Doğrulama: beyaz dalga formunun merkezi gövde merkezinde mi
let white = opaqueBounds(rep) { c in
    let c = c.usingColorSpace(.deviceRGB)!
    return c.redComponent > 0.97 && c.greenComponent > 0.97 && c.blueComponent > 0.97 && c.alphaComponent > 0.97
}
print("dalga formu merkezi: (\(white.midX), \(white.midY)), gövde merkezi: (\(body.midX), \(body.midY))")

try! rep.representation(using: .png, properties: [:])!
    .write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
