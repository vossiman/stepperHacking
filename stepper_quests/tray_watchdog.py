"""Verify the tray icon actually landed in the StatusNotifierWatcher.

At login, Qt can create its StatusNotifierItem while the watcher
(xapp-sn-watcher on Cinnamon) is still starting up: isSystemTrayAvailable()
returns True and show() succeeds, yet the item never makes it into the
watcher's registered list: no icon appears and nothing reports an error.
The watcher only accepts registrations from the item's own bus connection,
so the recovery is to hide()/show() the QSystemTrayIcon, which makes Qt
re-register from scratch.
"""

import logging
from collections.abc import Callable, Iterable

from PySide6.QtCore import SLOT, QObject, Slot
from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBusServiceWatcher

logger = logging.getLogger(__name__)

WATCHER_SERVICE = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
DBUS_SERVICE = "org.freedesktop.DBus"
DBUS_PATH = "/org/freedesktop/DBus"


def owns_registered_item(
    pid: int, items: Iterable[str], pid_of_service: Callable[[str], int | None]
) -> bool:
    """True if any watcher entry (e.g. ":1.76/StatusNotifierItem") belongs to pid."""
    for item in items:
        service = item.split("/", 1)[0]
        if service and pid_of_service(service) == pid:
            return True
    return False


def tray_registration_ok(pid: int) -> bool | None:
    """Whether pid owns a registered StatusNotifierItem; None if unverifiable
    (no session bus or no SNI watcher, e.g. an XEmbed-only tray)."""
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return None
    iface = bus.interface()
    if not iface.isServiceRegistered(WATCHER_SERVICE).value():
        return None
    msg = QDBusMessage.createMethodCall(
        WATCHER_SERVICE, WATCHER_PATH, "org.freedesktop.DBus.Properties", "Get"
    )
    msg.setArguments([WATCHER_SERVICE, "RegisteredStatusNotifierItems"])
    reply = bus.call(msg)
    if reply.type() != QDBusMessage.MessageType.ReplyMessage or not reply.arguments():
        logger.debug("could not read RegisteredStatusNotifierItems: %s", reply.errorMessage())
        return None
    items = reply.arguments()[0]
    if hasattr(items, "variant"):
        items = items.variant()
    if not isinstance(items, list):
        logger.debug("unexpected RegisteredStatusNotifierItems payload: %r", items)
        return None

    def pid_of(service: str) -> int | None:
        pid_reply = iface.servicePid(service)
        return pid_reply.value() if pid_reply.isValid() else None

    return owns_registered_item(pid, items, pid_of)


def watch_watcher_restarts(
    on_restart: Callable[[], None], parent: QObject | None = None, bus: QDBusConnection | None = None
) -> QDBusServiceWatcher | None:
    """Call on_restart whenever a StatusNotifierWatcher (re)appears on the bus;
    a fresh watcher starts with an empty item list. None without a session bus."""
    bus = bus if bus is not None else QDBusConnection.sessionBus()
    if not bus.isConnected():
        return None
    watcher = QDBusServiceWatcher(
        WATCHER_SERVICE, bus, QDBusServiceWatcher.WatchModeFlag.WatchForRegistration, parent
    )
    watcher.serviceRegistered.connect(lambda *_: on_restart())
    return watcher


def drops_item_of(vanished: str, own_service: str) -> bool:
    """True if xapp-sn-watcher before 3.3.5 wrongly drops own_service's item when
    vanished leaves the bus. It removes the first item whose key merely starts
    with the vanished name, so ":1.14" exiting deletes ":1.143/StatusNotifierItem"
    (fixed upstream in linuxmint/xapp 60d8f52)."""
    return vanished != own_service and own_service.startswith(vanished)


class _PrefixDisconnectListener(QObject):
    def __init__(self, own_service: str, on_drop: Callable[[str], None], parent: QObject | None) -> None:
        super().__init__(parent)
        self._own_service = own_service
        self._on_drop = on_drop

    @Slot(str, str, str)
    def on_name_owner_changed(self, name: str, _old_owner: str, new_owner: str) -> None:
        if not new_owner and drops_item_of(name, self._own_service):
            self._on_drop(name)


def watch_prefix_disconnects(
    on_drop: Callable[[str], None], parent: QObject | None = None, bus: QDBusConnection | None = None
) -> QObject | None:
    """Call on_drop(name) when a bus client whose name would make xapp-sn-watcher
    drop our item disconnects. None without a session bus."""
    bus = bus if bus is not None else QDBusConnection.sessionBus()
    if not bus.isConnected():
        return None
    listener = _PrefixDisconnectListener(bus.baseService(), on_drop, parent)
    connected = bus.connect(
        DBUS_SERVICE,
        DBUS_PATH,
        DBUS_SERVICE,
        "NameOwnerChanged",
        listener,
        # The stub says bytes, but PySide6 only accepts the str SLOT() returns.
        SLOT("on_name_owner_changed(QString,QString,QString)"),  # pyright: ignore[reportArgumentType]
    )
    if not connected:
        logger.warning("could not subscribe to NameOwnerChanged; tray drops will go unnoticed")
        listener.deleteLater()
        return None
    return listener
