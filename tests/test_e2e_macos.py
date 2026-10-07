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
