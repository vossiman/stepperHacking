"""BLE protocol constants and frame decoding for the Sportstech DFX100 stepper."""

STEPPER_MAC = ""  # set in the tray app settings; empty means "not configured"

SVC_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"

# In the 19-byte F0 B2 metrics frame, byte 9 is the only live field (cadence).
SPM_BYTE = 9
SPM_IDLE = 1  # raw values <= this mean "not stepping"
MIN_METRICS_LEN = 14

INIT_SEQUENCE: list[bytes] = [
    bytes.fromhex("f0a0000090"),
    bytes.fromhex("f0a0010192"),
    bytes.fromhex("f0a1010193"),
    bytes.fromhex("f0a50101049b"),
    bytes.fromhex("f0a501010299"),
    bytes.fromhex("f0a2010194"),
]
POLL: bytes = bytes.fromhex("f0a2010194")
POLL_INTERVAL = 0.5  # seconds, matches the vendor app


def checksum(body: bytes) -> int:
    return sum(body) & 0xFF


def parse_cadence(frame: bytes) -> int | None:
    """Steps per minute from a metrics frame, or None if it is not one."""
    if len(frame) < MIN_METRICS_LEN or frame[0] != 0xF0 or frame[1] != 0xB2:
        return None
    raw = frame[SPM_BYTE]
    return 0 if raw <= SPM_IDLE else raw
