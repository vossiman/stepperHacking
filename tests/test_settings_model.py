import pytest

from stepper_quests.settings_model import parse_mac


@pytest.mark.parametrize("text, expected", [
    ("AA:BB:CC:DD:EE:87", "AA:BB:CC:DD:EE:87"),
    ("aa:bb:cc:dd:ee:87", "AA:BB:CC:DD:EE:87"),
    ("  aa:bb:cc:dd:ee:ff  ", "AA:BB:CC:DD:EE:FF"),
])
def test_parse_mac_accepts_and_uppercases(text, expected):
    assert parse_mac(text) == expected


@pytest.mark.parametrize("text", [
    "",
    "AA:BB:CC:DD:EE",
    "AA:BB:CC:DD:EE:87:00",
    "18-7A-93-0B-7C-87",
    "187A930B7C87",
    "AA:BB:CC:DD:EE:8G",
    "1:7A:93:0B:7C:87",
])
def test_parse_mac_rejects_malformed(text):
    assert parse_mac(text) is None
