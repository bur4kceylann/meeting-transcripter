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
