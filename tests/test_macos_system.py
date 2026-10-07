import subprocess
import sys

import pytest

from src.ui.macos_system import notification_command

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="yalnızca macOS")


def test_notification_command_escapes_quotes_and_turkish():
    cmd = notification_command('Transkript "hazır"', 'kayıt_ğüşiöç \\ "x".txt')
    assert cmd[:2] == ["osascript", "-e"]
    # AppleScript derlenebilir olmalı: bildirim göstermeden sözdizimini kontrol et
    script = cmd[2].replace("display notification", "return")
    script = script.split(" with title ")[0]
    out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == 'kayıt_ğüşiöç \\ "x".txt'
