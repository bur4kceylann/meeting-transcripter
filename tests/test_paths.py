from pathlib import Path

from src.app import paths


def test_source_checkout_uses_project_dirs():
    p = paths.resolve(frozen=False)
    root = Path(paths.__file__).resolve().parents[2]
    assert p.models == root / "models"
    assert p.output == root / "output"
    assert p.logs == root / "logs"
    assert p.state == root / ".state"


def test_frozen_macos_uses_user_dirs():
    home = Path("/Users/mudur")
    p = paths.resolve(frozen=True, platform="darwin", home=home, env={})
    assert p.models == home / "Library/Application Support/Transkript/models"
    assert p.output == home / "Documents/Transkriptler"
    assert p.logs == home / "Library/Logs/Transkript"
    assert p.state == home / "Library/Application Support/Transkript"


def test_frozen_windows_uses_localappdata():
    home = Path("C:/Users/mudur")
    env = {"LOCALAPPDATA": "C:/Users/mudur/AppData/Local"}
    p = paths.resolve(frozen=True, platform="win32", home=home, env=env)
    assert p.models == Path("C:/Users/mudur/AppData/Local/Transkript/models")
    assert p.output == home / "Documents/Transkriptler"
    assert p.logs == Path("C:/Users/mudur/AppData/Local/Transkript/logs")


def test_ensure_creates_dirs(tmp_path):
    p = paths.AppPaths(
        models=tmp_path / "m", output=tmp_path / "o", logs=tmp_path / "l", state=tmp_path / "s"
    )
    assert p.ensure() is p
    for d in (p.models, p.output, p.logs, p.state):
        assert d.is_dir()
