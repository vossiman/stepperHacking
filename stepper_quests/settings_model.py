"""Pure validation for the settings dialog."""

import re

_MAC = re.compile(r"[0-9A-F]{2}(?::[0-9A-F]{2}){5}")


def parse_mac(text: str) -> str | None:
    """Return the MAC as AA:BB:CC:DD:EE:FF, or None if it is not one."""
    mac = text.strip().upper()
    return mac if _MAC.fullmatch(mac) else None
