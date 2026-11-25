"""Tests for tray registration verification against the StatusNotifierWatcher."""

from stepper_quests.tray_watchdog import _PrefixDisconnectListener, drops_item_of, owns_registered_item

ITEMS = [
    ":1.127/StatusNotifierItem",
    ":1.76/StatusNotifierItem",
    ":1.68/org/ayatana/NotificationItem/polychromatic_tray_applet",
]


def test_owns_registered_item_true_when_pid_matches() -> None:
    resolver = {":1.127": 111, ":1.76": 222, ":1.68": 333}.get
    assert owns_registered_item(222, ITEMS, resolver)


def test_owns_registered_item_false_when_pid_absent() -> None:
    resolver = {":1.127": 111, ":1.76": 222, ":1.68": 333}.get
    assert not owns_registered_item(999, ITEMS, resolver)


def test_owns_registered_item_matches_gtk_style_object_paths() -> None:
    resolver = {":1.68": 333}.get
    assert owns_registered_item(333, [":1.68/org/ayatana/NotificationItem/x"], resolver)


def test_owns_registered_item_ignores_unresolvable_names() -> None:
    assert not owns_registered_item(1, ITEMS, lambda name: None)


def test_owns_registered_item_empty_list() -> None:
    assert not owns_registered_item(1, [], lambda name: 1)


def test_watch_watcher_restarts_none_without_bus() -> None:
    from PySide6.QtDBus import QDBusConnection

    from stepper_quests.tray_watchdog import watch_watcher_restarts

    disconnected = QDBusConnection("stepper-quests-test-never-connected")
    assert watch_watcher_restarts(lambda: None, bus=disconnected) is None


def test_drops_item_of_matches_xapp_prefix_bug() -> None:
    assert drops_item_of(":1.14", ":1.143")
    assert drops_item_of(":1.1", ":1.143")


def test_drops_item_of_ignores_self_and_unrelated_names() -> None:
    assert not drops_item_of(":1.143", ":1.143")
    assert not drops_item_of(":1.144", ":1.143")
    assert not drops_item_of(":1.1430", ":1.143")
    assert not drops_item_of("org.kde.StatusNotifierItem-1-1", ":1.143")


def test_prefix_listener_fires_only_on_disconnect_of_a_prefix() -> None:
    dropped: list[str] = []
    listener = _PrefixDisconnectListener(":1.143", dropped.append, None)

    listener.on_name_owner_changed(":1.14", ":1.14", "")
    listener.on_name_owner_changed(":1.15", ":1.15", "")
    listener.on_name_owner_changed(":1.14", "", ":1.14")

    assert dropped == [":1.14"]


def test_watch_prefix_disconnects_none_without_bus() -> None:
    from PySide6.QtDBus import QDBusConnection

    from stepper_quests.tray_watchdog import watch_prefix_disconnects

    disconnected = QDBusConnection("stepper-quests-test-never-connected")
    assert watch_prefix_disconnects(lambda name: None, bus=disconnected) is None
