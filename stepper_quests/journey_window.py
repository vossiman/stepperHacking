"""Journey window: hero, live walk and today panels, and tabs for the rest."""

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QScrollArea, QStackedWidget, QTableWidget, QTableWidgetItem,
    QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QVBoxLayout, QWidget,
)

from . import journey_model as jm
from .bars_widget import BarsWidget
from .copy import format_steps
from .progress import ACHIEVEMENTS, HOBBITS_PACE_DAYS, RANGERS_DAYS
from .quests import miles_to_steps, steps_to_miles
from .route_widget import RouteWidget
from .tab_bar import TabBar

BRASS = "#d8b35a"
TEXT = "#e8e2d4"
MUTED = "#8f8878"
DIM = "#5f5a50"

STYLE = f"""
QWidget {{ font-family: "Noto Sans", "DejaVu Sans", "Liberation Sans", sans-serif; }}
QDialog, QWidget#content, QScrollArea {{ background: #1b1a17; color: {TEXT}; }}
QLabel {{ color: {TEXT}; background: transparent; }}
QLabel#breadcrumb {{ color: {MUTED}; font-size: 10pt; letter-spacing: 1px; }}
QLabel#leg {{ color: {TEXT}; font-family: "Noto Serif", "DejaVu Serif", serif; font-size: 22pt; }}
QLabel#sub {{ color: {MUTED}; font-size: 10pt; }}
QLabel#heading {{ color: {BRASS}; font-family: "Noto Serif", "DejaVu Serif", serif; font-size: 13pt; }}
QFrame#panel {{ background: #24221e; border: 1px solid #34312b; border-radius: 8px; }}
QLabel#panelTitle {{ color: {MUTED}; font-size: 10pt; }}
QLabel#tileValue {{ color: {BRASS}; font-size: 17pt; }}
QLabel#tileSub {{ color: {TEXT}; font-size: 9pt; }}
QLabel#pill {{ color: {MUTED}; background: #2e2b25; border: 1px solid #3a372f;
    border-radius: 9px; padding: 1px 8px; font-size: 8pt; }}
QLabel#lineLabel {{ color: {MUTED}; font-size: 9pt; }}
QLabel#lineValue {{ color: {TEXT}; font-size: 9pt; }}
QLabel#achTitle {{ font-size: 11pt; }}
QLabel#achBody {{ color: {MUTED}; font-size: 9pt; }}
QLabel#achDate {{ color: {BRASS}; font-size: 9pt; }}
QTreeWidget, QTableWidget {{ background: #24221e; color: {TEXT}; border: 1px solid #34312b;
    border-radius: 8px; padding: 4px; }}
QTreeWidget::item {{ padding: 3px 0; }}
QTreeWidget::item:selected {{ background: #3a352a; color: {TEXT}; }}
QTableWidget {{ gridline-color: #34312b; font-size: 9pt; }}
QHeaderView::section {{ background: #24221e; color: {MUTED}; border: none; padding: 4px; }}
QScrollBar:vertical {{ background: #1b1a17; width: 10px; }}
QScrollBar::handle:vertical {{ background: #3a372f; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""

MARKS = {"done": "✓", "active": "▶", "ahead": "·"}
COLOURS = {"done": MUTED, "active": BRASS, "ahead": TEXT}
TABS = ["Journey", "Achievements", "Records", "History"]
TAB_SETTING = "journey_tab"
STREAK_GOALS = {"hobbits-pace": HOBBITS_PACE_DAYS, "rangers-of-the-north": RANGERS_DAYS}
WALK_LINES = ("Length", "Pace", "Reached")
HISTORY_COLUMNS = ("Day", "Steps", "Walks", "Minutes", "Mean spm", "Reached")
ROW_HEIGHT = 24
REACHED_NAMES = 3
DEFAULT_HEIGHT = 820
MIN_HEIGHT = 600
SCREEN_MARGIN = 60
TABLE_PADDING = 8
RECORD_COLUMNS = (("records", "Records"), ("totals", "Totals"), ("pace", "Pace"))


def _label(text: str = "", name: str = "") -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    return label


def _panel() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("panel")
    box = QVBoxLayout(frame)
    box.setContentsMargins(14, 10, 14, 12)
    box.setSpacing(4)
    return frame, box


def _page() -> QWidget:
    page = QWidget()
    page.setObjectName("content")
    return page


def _scroll_area() -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    return scroll


def _clear(layout) -> None:
    while layout.count():
        widget = layout.takeAt(0).widget()
        if widget is not None:
            widget.deleteLater()


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _day_text(d: date) -> str:
    # Spelled out rather than strftime so the system locale cannot change it.
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def _short_day(d: date) -> str:
    return f"{jm.DAY_NAMES[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def _minutes(minutes: float) -> str:
    total = round(minutes)
    if total < 60:
        return f"{total} min"
    hours, rest = divmod(total, 60)
    return f"{hours} h {rest:02d} min"


def _walks(n: int) -> str:
    if n == 0:
        return "no walks yet"
    return f"{n} walk{'' if n == 1 else 's'}"


class JourneyWindow(QDialog):
    def __init__(self, store, quest, settings, parent=None):
        super().__init__(parent)
        self.store = store
        self.quest = quest
        self.settings = settings
        self._tree_filled = False
        self._centre_pending = False
        self._focus = None
        self._active_item = None
        self._active_key = None
        self._achievements_key = None
        self.setWindowTitle(f"Stepper Quests: {quest.title}")
        self.setStyleSheet(STYLE)
        self.setMinimumHeight(MIN_HEIGHT)
        height = DEFAULT_HEIGHT
        screen = self.screen()
        if screen is not None:
            height = min(height, screen.availableGeometry().height() - SCREEN_MARGIN)
        self.resize(900, max(MIN_HEIGHT, height))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 16)
        layout.setSpacing(8)

        self.breadcrumb = _label(name="breadcrumb")
        self.leg = _label(name="leg")
        self.sub = _label(name="sub")
        layout.addWidget(self.breadcrumb)
        layout.addWidget(self.leg)
        layout.addWidget(self.sub)
        route_panel = QFrame()
        route_panel.setObjectName("panel")
        route_box = QVBoxLayout(route_panel)
        route_box.setContentsMargins(8, 8, 8, 8)
        self.route = RouteWidget()
        route_box.addWidget(self.route)
        layout.addWidget(route_panel)

        panels = QHBoxLayout()
        panels.setSpacing(10)
        panels.addWidget(self._build_walk_panel(), 1)
        panels.addWidget(self._build_today_panel(), 1)
        layout.addLayout(panels)

        self.tab_bar = TabBar(TABS)
        layout.addWidget(self.tab_bar)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_journey_page())
        self.pages.addWidget(self._build_achievements_page())
        self.pages.addWidget(self._build_records_page())
        self.pages.addWidget(self._build_history_page())
        layout.addWidget(self.pages, 1)

        self.refresh()
        self.tab_bar.changed.connect(lambda name: self.pages.setCurrentIndex(TABS.index(name)))
        tab = store.get_setting(TAB_SETTING, TABS[0])
        self.tab_bar.select(tab if tab in TABS else TABS[0])
        self.tab_bar.changed.connect(lambda name: self.store.set_setting(TAB_SETTING, name))

    # building

    def _panel_header(self, box: QVBoxLayout) -> tuple[QLabel, QLabel]:
        row = QHBoxLayout()
        title = _label(name="panelTitle")
        pill = QLabel()
        pill.setObjectName("pill")
        row.addWidget(title, 1)
        row.addWidget(pill, 0, Qt.AlignRight)
        box.addLayout(row)
        return title, pill

    def _build_walk_panel(self) -> QFrame:
        self.walk_panel, box = _panel()
        self.walk_title, self.walk_pill = self._panel_header(box)
        self.walk_value = _label(name="tileValue")
        self.walk_sub = _label(name="tileSub")
        box.addWidget(self.walk_value)
        box.addWidget(self.walk_sub)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(1, 1)
        self.walk_lines: dict[str, tuple[QLabel, QLabel]] = {}
        for row, name in enumerate(WALK_LINES):
            key, value = _label(name, "lineLabel"), _label(name="lineValue")
            key.setWordWrap(False)
            grid.addWidget(key, row, 0, Qt.AlignTop)
            grid.addWidget(value, row, 1)
            self.walk_lines[name] = (key, value)
        box.addLayout(grid)
        box.addStretch(1)
        return self.walk_panel

    def _build_today_panel(self) -> QFrame:
        panel, box = _panel()
        title, self.today_pill = self._panel_header(box)
        title.setText("Today")
        self.today_value = _label(name="tileValue")
        self.today_bars = BarsWidget()
        self.today_week = _label(name="tileSub")
        box.addWidget(self.today_value)
        box.addWidget(self.today_bars)
        box.addWidget(self.today_week)
        box.addStretch(1)
        return panel

    def _build_journey_page(self) -> QWidget:
        page = _page()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 8, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.setRootIsDecorated(True)
        box.addWidget(self.tree)
        return page

    def _build_achievements_page(self) -> QWidget:
        self.achievements_scroll = _scroll_area()
        content = _page()
        self.achievements_grid = QGridLayout(content)
        self.achievements_grid.setContentsMargins(0, 8, 4, 0)
        self.achievements_grid.setSpacing(10)
        self.achievements_grid.setColumnStretch(0, 1)
        self.achievements_grid.setColumnStretch(1, 1)
        self.achievements_scroll.setWidget(content)
        return self.achievements_scroll

    def _build_records_page(self) -> QWidget:
        scroll = _scroll_area()
        page = _page()
        scroll.setWidget(page)
        row = QHBoxLayout(page)
        row.setContentsMargins(0, 8, 0, 0)
        row.setSpacing(10)
        self.record_forms: dict[str, QFormLayout] = {}
        for key, heading in RECORD_COLUMNS:
            panel, box = _panel()
            box.addWidget(_label(heading, "heading"))
            form = QFormLayout()
            form.setHorizontalSpacing(10)
            form.setVerticalSpacing(4)
            form.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
            box.addLayout(form)
            box.addStretch(1)
            self.record_forms[key] = form
            row.addWidget(panel, 1, Qt.AlignTop)
        return scroll

    def _build_history_page(self) -> QWidget:
        scroll = _scroll_area()
        page = _page()
        scroll.setWidget(page)
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 8, 0, 0)
        box.setSpacing(6)
        self.history_bars = BarsWidget()
        self.history_line = _label(name="sub")
        self.history_table = QTableWidget(0, len(HISTORY_COLUMNS))
        table = self.history_table
        table.setHorizontalHeaderLabels(HISTORY_COLUMNS)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.setShowGrid(False)
        table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        header = table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for column in range(len(HISTORY_COLUMNS) - 1):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        box.addWidget(self.history_bars)
        box.addWidget(self.history_line)
        box.addWidget(table)
        box.addStretch(1)
        return scroll

    # data

    def refresh(self) -> None:
        mps = self.settings.metres_per_step
        today = date.today()
        miles = steps_to_miles(self.store.lifetime_steps(), mps)
        position = self.quest.position(miles)

        chapter, part = position.chapter, position.part
        self.breadcrumb.setText(
            f"{part.volume.title.upper()}  ·  {part.title.upper()}  ·  {chapter.title.upper()}"
        )
        if position.next is None:
            self.leg.setText(f"{chapter.leg}. The road ends here.")
        else:
            steps = miles_to_steps(position.miles_to_next, mps)
            self.leg.setText(f"{chapter.leg}, {format_steps(steps)} steps to {position.next.name}")
        walked = self.store.first_session_start() is not None
        pace = jm.pace_steps_per_day(self.store, today)
        self.sub.setText(jm.projection_line(self.quest, position, mps, pace if walked else None))

        first = part.chapters[0].waypoints[0]
        self.route.set_part(part, position, miles,
                            start_miles=jm.stretch_start(self.quest, first))

        self._fill_walk(position, today, mps)
        self._fill_today(today)
        self._fill_tree(position, miles, mps, pace)
        self._fill_achievements(today)
        self._fill_records(position, today, mps)
        self._fill_history(today)

    def _fill_walk(self, position, today: date, mps: float) -> None:
        walk = jm.latest_walk(self.store, self.quest)
        lines_visible = walk is not None
        for key, value in self.walk_lines.values():
            key.setVisible(lines_visible)
            value.setVisible(lines_visible)
        self.walk_sub.setVisible(not lines_visible)
        self.walk_pill.setVisible(lines_visible)
        if walk is None:
            self.walk_title.setText("Last walk")
            self.walk_value.setText("No walks yet")
            self.walk_sub.setText("Start stepping and this fills in.")
            return
        self.walk_title.setText("Walking now" if walk.live else "Last walk")
        self.walk_pill.setText(jm.start_pill(walk.start, today))
        self.walk_value.setText(f"{format_steps(walk.steps)} steps")
        if len(walk.reached) > REACHED_NAMES:
            more = len(walk.reached) - REACHED_NAMES
            reached = f"{', '.join(walk.reached[:REACHED_NAMES])} and {more} more"
        elif walk.reached:
            reached = ", ".join(walk.reached)
        elif position.next is None:
            reached = "nothing new"
        else:
            to_go = miles_to_steps(position.miles_to_next, mps)
            reached = f"nothing new, {format_steps(to_go)} to go"
        values = {
            "Length": _minutes(walk.minutes),
            "Pace": f"{walk.mean_spm:.0f} spm mean, {walk.max_spm} peak",
            "Reached": reached,
        }
        for name, text in values.items():
            self.walk_lines[name][1].setText(text)

    def walk_panel_text(self) -> str:
        labels = self.walk_panel.findChildren(QLabel)
        return "\n".join(label.text() for label in labels
                         if not label.isHidden() and label.text())

    def current_tab(self) -> str:
        return self.tab_bar.current()

    def _fill_today(self, today: date) -> None:
        day = jm.today_stats(self.store, today)
        self.today_pill.setText(_walks(day.sessions))
        self.today_value.setText(f"{format_steps(day.steps)} steps")
        week = jm.week_stats(self.store, today)
        self.today_bars.set_values(week.last7, week.labels)
        self.today_week.setText(jm.week_line(week))

    def _item(self, parent, name: str, detail: str, state: str, bold: bool = False):
        item = QTreeWidgetItem(parent, [f"{MARKS[state]}  {name}", detail])
        colour = QBrush(QColor(COLOURS[state]))
        item.setForeground(0, colour)
        item.setForeground(1, colour)
        item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
        if bold or state == "active":
            font = QFont(self.tree.font())
            font.setBold(True)
            item.setFont(0, font)
        return item

    def _expanded_keys(self) -> set[tuple]:
        keys = set()
        it = QTreeWidgetItemIterator(self.tree)
        while it.value() is not None:
            item = it.value()
            key = item.data(0, Qt.UserRole)
            if key is not None and item.isExpanded():
                keys.add(tuple(key))
            it += 1
        return keys

    def _fill_tree(self, position, miles: float, mps: float, pace: float) -> None:
        expanded = self._expanded_keys()
        scroll = self.tree.verticalScrollBar().value()
        self.tree.clear()
        keyed = []
        active_item = focus = active_key = None
        for volume in self.quest.volumes:
            v_states = [jm.chapter_state(c, position) for p in volume.parts for c in p.chapters]
            v_item = self._item(self.tree, volume.title, "", _rollup(v_states), bold=True)
            keyed.append((v_item, (volume.title, None, None)))
            for part in volume.parts:
                p_states = [jm.chapter_state(c, position) for c in part.chapters]
                p_item = self._item(v_item, part.title, "", _rollup(p_states))
                keyed.append((p_item, (volume.title, part.title, None)))
                for chapter in part.chapters:
                    state = jm.chapter_state(chapter, position)
                    est = jm.chapter_estimate(self.quest, chapter, mps, pace)
                    c_item = self._item(p_item, f"{chapter.title}: {chapter.leg}",
                                        jm.chapter_label(est), state)
                    keyed.append((c_item, (volume.title, part.title, chapter.title)))
                    if state != "active":
                        continue
                    active_item = c_item
                    active_key = (volume.title, part.title, chapter.title)
                    for w in chapter.waypoints:
                        w_state = jm.waypoint_state(w, position)
                        if w_state == "done":
                            detail = "reached"
                        else:
                            steps = miles_to_steps(w.walkable_miles - miles, mps)
                            detail = f"{format_steps(steps)} steps to go"
                        w_item = self._item(c_item, w.name, detail, w_state)
                        if w_state == "active":
                            focus = w_item
        for item, key in keyed:
            item.setData(0, Qt.UserRole, key)
        self._focus = focus
        self._active_item = active_item
        chapter_changed = active_key != self._active_key
        self._active_key = active_key
        if not self._tree_filled:
            self._tree_filled = True
            self._centre_active()
            return
        for item, key in keyed:
            item.setExpanded(key in expanded)
        self.tree.doItemsLayout()
        self.tree.verticalScrollBar().setValue(scroll)
        if chapter_changed:
            self._centre_active()

    def _centre_active(self) -> None:
        item = self._active_item
        while item is not None:
            item.setExpanded(True)
            item = item.parent()
        if not self.isVisible():
            # The viewport has its real height only once shown, so showEvent centres.
            self._centre_pending = True
            return
        self._centre_pending = False
        if self._focus is not None:
            self.tree.doItemsLayout()
            self.tree.scrollToItem(self._focus, QTreeWidget.PositionAtCenter)

    def _fill_achievements(self, today: date) -> None:
        status = jm.achievement_status(ACHIEVEMENTS, self.store.unlocked())
        streak = self.store.streak_days(today)
        key = (tuple(sorted(status.items())), streak)
        if key == self._achievements_key:
            return
        self._achievements_key = key
        _clear(self.achievements_grid)
        ordered = sorted(ACHIEVEMENTS, key=lambda a: status[a.name] is None)
        for i, a in enumerate(ordered):
            unlocked = status[a.name]
            panel, box = _panel()
            title = _label(a.title, "achTitle")
            box.addWidget(title)
            if unlocked is not None:
                box.addWidget(_label(a.body, "achBody"))
                box.addWidget(_label(_unlocked_text(*unlocked), "achDate"))
            else:
                body = _label(a.condition, "achBody")
                title.setStyleSheet(f"color: {DIM};")
                body.setStyleSheet(f"color: {DIM};")
                box.addWidget(body)
                goal = STREAK_GOALS.get(a.name)
                if goal is not None:
                    box.addWidget(_label(f"{min(streak, goal)} of {goal}", "achBody"))
            box.addStretch(1)
            self.achievements_grid.addWidget(panel, i // 2, i % 2)
        self.achievements_grid.setRowStretch((len(ordered) + 1) // 2, 1)

    def _fill_records(self, position, today: date, mps: float) -> None:
        recs = jm.records(self.store, self.quest, position, mps, today)
        for key, form in self.record_forms.items():
            while form.rowCount():
                form.removeRow(0)
            for name, value in getattr(recs, key):
                label = _label(name, "lineLabel")
                label.setWordWrap(False)
                form.addRow(label, _label(value, "lineValue"))

    def _fill_history(self, today: date) -> None:
        days = [today - timedelta(days=n) for n in range(jm.HISTORY_DAYS - 1, -1, -1)]
        self.history_bars.set_values([self.store.steps_on_day(d) for d in days])
        rows = jm.history_days(self.store, self.quest, today)
        if rows:
            self.history_line.setText(jm.walking_days_text(rows))
        else:
            self.history_line.setText("Last 30 days. No walks yet.")
        table = self.history_table
        table.setRowCount(len(rows))
        # The page scrolls, not the table, so the table is exactly as tall as its rows.
        table.setFixedHeight(table.horizontalHeader().sizeHint().height()
                             + ROW_HEIGHT * len(rows) + 2 * table.frameWidth() + TABLE_PADDING)
        for r, row in enumerate(rows):
            walked = row.walks > 0
            cells = [
                _short_day(row.day),
                format_steps(row.steps),
                str(row.walks),
                f"{round(row.minutes)}" if walked else "",
                f"{row.mean_spm:.0f}" if walked else "",
                ", ".join(row.reached),
            ]
            colour = QBrush(QColor(TEXT if walked else MUTED))
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setForeground(colour)
                table.setItem(r, c, item)

    # navigation

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._centre_pending:
            self._centre_active()

    def show_section(self, name: str) -> None:
        if name == "achievements":
            self.tab_bar.select("Achievements")
            return
        self.tab_bar.select("Journey")
        self._centre_active()


def _rollup(states: list[str]) -> str:
    if states and all(s == "done" for s in states):
        return "done"
    if "active" in states:
        return "active"
    return "ahead"


def _unlocked_text(at: float, note: str) -> str:
    when = _day_text(datetime.fromtimestamp(at).date())
    if note.isdigit():
        return f"{when}, {format_steps(int(note))} steps"
    return f"{when}, {note}" if note else when
