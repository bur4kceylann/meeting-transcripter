"""Controller durumunu kısa menü çubuğu / tepsi metinlerine çevirir (saf fonksiyonlar)."""

from __future__ import annotations

from src.app.controller import Phase, State


def _pct(progress: float | None) -> int:
    return int((progress or 0.0) * 100)


def status_title(state: State, now: float) -> str:
    phase = state.phase
    if phase is Phase.DOWNLOADING:
        return f"⬇️ %{_pct(state.progress)}"
    if phase is Phase.RECORDING:
        seconds = max(0, int(now - (state.started_at if state.started_at is not None else now)))
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        return f"🔴 {hours}:{minutes:02d}:{secs:02d}" if hours else f"🔴 {minutes:02d}:{secs:02d}"
    if phase is Phase.TRANSCRIBING:
        return f"⏳ %{_pct(state.progress)}"
    if phase in (Phase.ERROR, Phase.NEEDS_MODEL):
        return "⚠️"
    return "🎙"


def toggle_label(state: State) -> str:
    return {
        Phase.RECORDING: "Kaydı Durdur",
        Phase.TRANSCRIBING: "Transkript üretiliyor…",
        Phase.DOWNLOADING: "Model indiriliyor…",
    }.get(state.phase, "Kaydı Başlat")
