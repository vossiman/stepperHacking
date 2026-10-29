import csv
from pathlib import Path

from stepper_quests import protocol

FIXTURE = Path(__file__).parent / "fixtures" / "frames.csv"


def load_frames() -> list[bytes]:
    with FIXTURE.open(newline="") as f:
        return [bytes.fromhex(row["hex"]) for row in csv.DictReader(f)]


def test_parse_cadence_from_recorded_frames():
    values = [protocol.parse_cadence(frame) for frame in load_frames()]
    assert any(v is not None and 50 <= v <= 70 for v in values)


def test_short_b0_frame_is_none():
    assert protocol.parse_cadence(bytes.fromhex("f0b000c868")) is None


def test_idle_raw_one_is_zero():
    frame = bytearray(19)
    frame[0], frame[1], frame[3] = 0xF0, 0xB2, 0xC8
    frame[9] = 1
    frame[18] = protocol.checksum(bytes(frame[:18]))
    assert protocol.parse_cadence(bytes(frame)) == 0


def test_checksum_matches_recorded_frames():
    b2 = [f for f in load_frames() if len(f) == 19 and f[:2] == b"\xf0\xb2"]
    assert b2
    for frame in b2:
        assert frame[-1] == protocol.checksum(frame[:-1])


def test_init_sequence_matches_readme():
    readme = [
        "f0a0000090",
        "f0a0010192",
        "f0a1010193",
        "f0a501010299",
        "f0a2010194",
    ]
    sequence = [frame.hex() for frame in protocol.INIT_SEQUENCE]
    remaining = iter(sequence)
    assert all(frame in remaining for frame in readme)
    assert protocol.POLL.hex() == "f0a2010194"
    assert sequence[-1] == "f0a2010194"
