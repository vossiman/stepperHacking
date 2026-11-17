from stepper_quests import journey_model as jm
from stepper_quests.overview_widget import OverviewBar
from stepper_quests.quests import Quest, load_quest


def test_percent_one_decimal(qapp):
    bar = OverviewBar()
    bar.set_overview(jm.Span(0.0, 458.0, []), ("Bag End", "Rivendell"), 6.0, 6.0 / 458.0)
    assert bar.percent_text() == "1.3%"
    bar.resize(800, 28)
    bar.grab()


def test_full_part_is_100(qapp):
    bar = OverviewBar()
    bar.set_overview(jm.Span(0.0, 10.0, []), ("A", "B"), 10.0, 1.0)
    assert bar.percent_text() == "100.0%"


def test_zero_length_span_and_clamped_fraction(qapp):
    bar = OverviewBar()
    bar.resize(800, 28)
    bar.set_overview(jm.Span(5.0, 5.0, []), ("A", "B"), 5.0, 1.7)
    assert bar.percent_text() == "100.0%"
    bar.grab()
    bar.set_overview(jm.Span(5.0, 5.0, []), ("A", "B"), 5.0, -0.2)
    assert bar.percent_text() == "0.0%"
    bar.grab()


def test_real_part_with_ticks_paints(qapp):
    quest = load_quest(Quest.default_path())
    part = quest.volumes[0].parts[0]
    span = jm.overview_span(quest, part)
    bar = OverviewBar()
    bar.resize(800, 28)
    bar.set_overview(span, jm.part_label_ends(quest, part), 6.0, 6.0 / span.end)
    assert not bar.grab().isNull()
