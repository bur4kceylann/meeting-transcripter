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
