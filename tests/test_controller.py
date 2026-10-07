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
