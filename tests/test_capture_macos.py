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


def _counting_helper(tmp_path, body: str):
    """Her çalıştırmada artan bir sayaç (run) ile sahte yardımcı."""
    counter = tmp_path / "runs"
    counter.write_text("0")
    prelude = (
        "import pathlib\n"
        f"_c = pathlib.Path({str(counter)!r})\n"
        "run = int(_c.read_text()) + 1\n"
        "_c.write_text(str(run))\n"
    )
    return _fake_helper(tmp_path, prelude + textwrap.dedent(body))


def test_helper_exit_mid_recording_restarts_and_continues(tmp_path):
    # Review #3: ses çıkışı değişince (AirPods) ya da yardımcı çökünce kayıt kesilmemeli
    helper = _counting_helper(
        tmp_path,
        """
        header(16000, 1)
        if run == 1:
            out.write(struct.pack('<f', 0.1) * 300); out.flush()
            sys.exit(75)
        out.write(struct.pack('<f', 0.3) * 200); out.flush()
        while True: time.sleep(0.05)
        """,
    )
    capture = MacOSCapture(helper=helper)
    audio = _record(capture, seconds=1.0)
    assert audio.shape == (500,)
    assert np.allclose(audio[:300], 0.1)
    assert np.allclose(audio[300:], 0.3)


def test_restart_with_different_samplerate_is_resampled(tmp_path):
    helper = _counting_helper(
        tmp_path,
        """
        if run == 1:
            header(16000, 1)
            out.write(struct.pack('<f', 0.1) * 1600); out.flush()
            sys.exit(75)
        header(8000, 1)
        out.write(struct.pack('<f', 0.3) * 800); out.flush()
        while True: time.sleep(0.05)
        """,
    )
    capture = MacOSCapture(helper=helper)
    audio = _record(capture, seconds=1.0)
    assert capture.samplerate == 16000
    assert audio.shape == (3200,)
    assert np.allclose(audio[1600:], 0.3)


def test_restart_keeps_failing_reports_interruption(tmp_path, monkeypatch):
    import src.audio.capture_macos as cm

    monkeypatch.setattr(cm, "_RESTART_DELAY", 0.01)
    helper = _counting_helper(
        tmp_path,
        """
        if run > 1:
            sys.exit(1)
        header(16000, 1)
        out.write(struct.pack('<f', 0.2) * 400); out.flush()
        sys.exit(75)
        """,
    )
    capture = MacOSCapture(helper=helper)
    interrupted = []
    capture.on_interrupted = lambda: interrupted.append(True)
    capture.start()
    deadline = time.monotonic() + 10
    while not interrupted and time.monotonic() < deadline:
        time.sleep(0.05)
    assert interrupted == [True]
    audio = capture.stop()
    assert audio.shape == (400,)


def test_header_timeout_raises_instead_of_hanging(tmp_path, monkeypatch):
    import src.audio.capture_macos as cm

    monkeypatch.setattr(cm, "_HEADER_TIMEOUT", 0.5)
    helper = _fake_helper(tmp_path, "while True: time.sleep(0.05)\n")
    started = time.monotonic()
    with pytest.raises(RuntimeError):
        MacOSCapture(helper=helper).start()
    assert time.monotonic() - started < 3
