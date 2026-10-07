"""macOS sistem entegrasyonları: bildirim, dosya/URL açma, oturum açılışında başlatma.

Paketli (imzalı) uygulamada UserNotifications ve SMAppService kullanılır;
kaynaktan çalışırken bunlar bundle gerektirdiği için bildirimler osascript ile
gösterilir ve oturum açılışında başlatma desteklenmez.
"""

from __future__ import annotations

import json
import logging
import subprocess
import uuid
from pathlib import Path

from src.app.paths import is_frozen

log = logging.getLogger(__name__)
_delegate = None  # UNUserNotificationCenter delegate'i zayıf referans tutar; burada canlı tut


def _applescript_string(text: str) -> str:
    # AppleScript string sözdizimi JSON ile aynı kaçışları (\" ve \\) kabul eder
    return json.dumps(text, ensure_ascii=False)


def notification_command(title: str, body: str) -> list[str]:
    script = f"display notification {_applescript_string(body)} with title {_applescript_string(title)}"
    return ["osascript", "-e", script]


def setup_notifications() -> None:
    """Bildirim izni ister ve uygulama öndeyken de banner gösterilmesini sağlar."""
    if not is_frozen():
        return
    global _delegate
    from Foundation import NSObject
    from UserNotifications import (
        UNAuthorizationOptionAlert,
        UNAuthorizationOptionSound,
        UNNotificationPresentationOptionBanner,
        UNNotificationPresentationOptionList,
        UNUserNotificationCenter,
    )

    class _Delegate(NSObject):
        def userNotificationCenter_willPresentNotification_withCompletionHandler_(self, center, notification, handler):
            handler(UNNotificationPresentationOptionBanner | UNNotificationPresentationOptionList)

    center = UNUserNotificationCenter.currentNotificationCenter()
    _delegate = _Delegate.alloc().init()
    center.setDelegate_(_delegate)
    center.requestAuthorizationWithOptions_completionHandler_(
        UNAuthorizationOptionAlert | UNAuthorizationOptionSound,
        lambda granted, error: log.info("Bildirim izni: %s %s", granted, error or ""),
    )


def notify(title: str, body: str) -> None:
    log.info("Bildirim: %s - %s", title, body)
    if not is_frozen():
        subprocess.run(notification_command(title, body), capture_output=True)
        return
    from UserNotifications import (
        UNMutableNotificationContent,
        UNNotificationRequest,
        UNUserNotificationCenter,
    )

    content = UNMutableNotificationContent.alloc().init()
    content.setTitle_(title)
    content.setBody_(body)
    request = UNNotificationRequest.requestWithIdentifier_content_trigger_(str(uuid.uuid4()), content, None)
    UNUserNotificationCenter.currentNotificationCenter().addNotificationRequest_withCompletionHandler_(
        request, lambda error: error and log.warning("Bildirim gösterilemedi: %s", error)
    )


def open_path(path: Path) -> None:
    subprocess.run(["open", str(path)])


def open_url(url: str) -> None:
    subprocess.run(["open", url])


def login_item_supported() -> bool:
    return is_frozen()


def login_item_enabled() -> bool:
    from ServiceManagement import SMAppService, SMAppServiceStatusEnabled

    return SMAppService.mainAppService().status() == SMAppServiceStatusEnabled


def set_login_item(enabled: bool) -> bool:
    from ServiceManagement import SMAppService

    service = SMAppService.mainAppService()
    ok, error = service.registerAndReturnError_(None) if enabled else service.unregisterAndReturnError_(None)
    if not ok:
        log.warning("Oturum açılışında başlatma ayarlanamadı (%s): %s", enabled, error)
    return bool(ok)
