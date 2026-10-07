"""Controller durumunu kısa menü çubuğu / tepsi metinlerine çevirir (saf fonksiyonlar)."""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class QuitConfirmation:
    title: str
    message: str
    stop_button: str | None  # verilirse: "çıkmadan önce kaydı durdurup metne çevir" seçeneği


def quit_confirmation(state: State) -> QuitConfirmation | None:
    """Çıkışta onay gerekiyorsa pencerenin metinleri; gerekmiyorsa None."""
    if state.phase is Phase.RECORDING:
        return QuitConfirmation(
            title="Kayıt sürüyor",
            message="Çıkarsan kayıt metne çevrilmez, yalnızca ses dosyası saklanır. "
                    "Önce kaydı durdurup metne çevirmek ister misin?",
            stop_button="Durdur ve Metne Çevir",
        )
    if state.phase is Phase.TRANSCRIBING:
        return QuitConfirmation(
            title="Transkript sürüyor",
            message="Çıkarsan transkript yarıda kalır; ses kaydı klasörde durur. Yine de çıkılsın mı?",
            stop_button=None,
        )
    return None
