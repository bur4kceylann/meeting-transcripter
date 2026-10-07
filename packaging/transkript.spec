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
