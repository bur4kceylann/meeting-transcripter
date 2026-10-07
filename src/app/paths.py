"""Uygulamanın kullandığı klasörler.

Paketli uygulamada (PyInstaller, sys.frozen) kullanıcı klasörleri, kaynaktan
çalışırken proje içi klasörler kullanılır; böylece geliştiricinin indirdiği
model ve çıktılar yerinde kalır.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Transkript"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AppPaths:
    models: Path
    output: Path
    logs: Path
    state: Path  # küçük ayar / işaret dosyaları

    def ensure(self) -> "AppPaths":
        for directory in (self.models, self.output, self.logs, self.state):
            directory.mkdir(parents=True, exist_ok=True)
        return self


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resolve(
    frozen: bool | None = None,
    platform: str | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> AppPaths:
    frozen = is_frozen() if frozen is None else frozen
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else home
    env = os.environ if env is None else env

    if not frozen:
        return AppPaths(
            models=_PROJECT_ROOT / "models",
            output=_PROJECT_ROOT / "output",
            logs=_PROJECT_ROOT / "logs",
            state=_PROJECT_ROOT / ".state",
        )
    output = home / "Documents" / "Transkriptler"
    if platform == "darwin":
        support = home / "Library" / "Application Support" / APP_NAME
        return AppPaths(models=support / "models", output=output,
                        logs=home / "Library" / "Logs" / APP_NAME, state=support)
    if platform == "win32":
        local = Path(env.get("LOCALAPPDATA", str(home / "AppData" / "Local"))) / APP_NAME
        return AppPaths(models=local / "models", output=output, logs=local / "logs", state=local)
    data = Path(env.get("XDG_DATA_HOME", str(home / ".local" / "share"))) / APP_NAME
    return AppPaths(models=data / "models", output=output, logs=data / "logs", state=data)
