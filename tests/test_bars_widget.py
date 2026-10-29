from stepper_quests.bars_widget import BarsWidget
from stepper_quests.tab_bar import TabBar


def test_bars_render_to_pixmap(qapp):
    w = BarsWidget()
    w.set_values([0, 100, 50], ["M", "T", "W"])
    w.resize(300, 72)
    assert not w.grab().isNull()


def test_tab_bar_selection(qapp):
    bar = TabBar(["Journey", "Records"])
    seen = []
    bar.changed.connect(seen.append)
    bar.select("Records")
    assert bar.current() == "Records" and seen == ["Records"]


def test_zero_last_bar_is_brass(qapp):
    w = BarsWidget()
    w.set_values([100, 0], highlight_last=True)
    w.resize(200, 56)
    img = w.grab().toImage()
    x = img.width() - 10
    y = img.height() - 1
    c = img.pixelColor(x, y)
    assert (c.red(), c.green(), c.blue()) == (0xD8, 0xB3, 0x5A)


def test_bars_render_empty_and_all_zero(qapp):
    w = BarsWidget()
    w.resize(200, 56)
    w.set_values([])
    assert not w.grab().isNull()
    w.set_values([0, 0])
    assert not w.grab().isNull()
