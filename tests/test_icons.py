import pytest

from stepper_quests.icons import STATES, make_icon, write_app_icon


def test_states():
    assert STATES == ("idle", "stepping", "reconnecting")


@pytest.mark.parametrize("state", ["idle", "stepping", "reconnecting"])
def test_icon_is_not_null_at_panel_sizes(state):
    icon = make_icon(state)
    assert not icon.isNull()
    for size in (22, 48):
        assert not icon.pixmap(size).toImage().isNull()


def test_icons_differ_per_state():
    images = [make_icon(s).pixmap(22).toImage() for s in ("idle", "stepping", "reconnecting")]
    assert images[0] != images[1]
    assert images[1] != images[2]
    assert images[0] != images[2]


def test_unknown_state_raises():
    with pytest.raises(KeyError):
        make_icon("disc")


def test_write_app_icon(tmp_path):
    path = tmp_path / "stepper-quests.svg"
    write_app_icon(path)
    assert path.read_text(encoding="utf-8").startswith("<svg")
