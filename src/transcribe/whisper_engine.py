"""faster-whisper sarmalayıcısı.

Bir ses dosyasını (WAV) alır, yerel Whisper modeliyle transkript eder ve
zaman damgalı segment listesi döndürür. Model dosyaları ilk kullanımda
`models/` klasörüne indirilir; sonraki çalıştırmalar tamamen offline'dır.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


@dataclass
class Segment:
    start: float  # saniye
    end: float
    text: str


@dataclass
class TranscriptResult:
    segments: list[Segment]
    language: str
    language_probability: float

    @property
    def text(self) -> str:
        return "\n".join(seg.text.strip() for seg in self.segments)


class WhisperEngine:
    def __init__(
        self,
        model_size: str = "medium",
        device: str = "auto",
        compute_type: str = "int8_float32",
    ) -> None:
        from faster_whisper import WhisperModel

        # Not: Apple Silicon'da ctranslate2 CPU backend'i float16/int8_float16
        # desteklemiyor (sadece CUDA'da var). CPU'da desteklenenler:
        # int8, int8_float32, float32. int8_float32 (int8 ağırlık + float32
        # biriktirme) saf int8'e göre daha doğru, float32'ye göre daha hızlı.
        _MODELS_DIR.mkdir(exist_ok=True)
        self.model_size = model_size
        self._model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=str(_MODELS_DIR),
        )

    def transcribe(self, audio_path: str | Path, language: str | None = None) -> TranscriptResult:
        """Ses dosyasını transkript eder.

        language None ise Whisper dili otomatik algılar (Türkçe dahil).
        """
        segments_iter, info = self._model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,  # sessiz bölümleri atla (toplantılarda uzun boşluklar olur)
        )
        segments = [Segment(start=s.start, end=s.end, text=s.text) for s in segments_iter]
        return TranscriptResult(
            segments=segments,
            language=info.language,
            language_probability=info.language_probability,
        )
