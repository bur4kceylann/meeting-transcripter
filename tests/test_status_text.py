from src.app.controller import ErrorKind, Phase, State
from src.ui.status_text import quit_confirmation, status_title, toggle_label


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


def test_quit_confirmation_only_while_working():
    # Review #4: kayıt sürerken de onay sorulmalı; boştayken sorulmamalı
    assert quit_confirmation(State(Phase.IDLE)) is None
    assert quit_confirmation(State(Phase.DOWNLOADING, progress=0.2)) is None
    recording = quit_confirmation(State(Phase.RECORDING, started_at=0))
    assert recording.title == "Kayıt sürüyor"
    assert recording.stop_button == "Durdur ve Metne Çevir"
    transcribing = quit_confirmation(State(Phase.TRANSCRIBING, progress=0.4))
    assert transcribing.title == "Transkript sürüyor"
    assert transcribing.stop_button is None
