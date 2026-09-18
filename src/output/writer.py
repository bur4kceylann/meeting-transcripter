"""Transkript sonucunu .txt ve zaman damgalı .srt olarak kaydeder."""

from __future__ import annotations

from pathlib import Path

from src.transcribe.whisper_engine import TranscriptResult


def format_srt_timestamp(seconds: float) -> str:
    """Saniyeyi SRT zaman biçimine çevirir: HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0.0
    total_ms = round(seconds * 1000)
    ms = total_ms % 1000
    total_s = total_ms // 1000
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_txt(result: TranscriptResult, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.text + "\n", encoding="utf-8")
    return path


def write_srt(result: TranscriptResult, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for i, seg in enumerate(result.segments, start=1):
        blocks.append(
            f"{i}\n"
            f"{format_srt_timestamp(seg.start)} --> {format_srt_timestamp(seg.end)}\n"
            f"{seg.text.strip()}\n"
        )
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path
