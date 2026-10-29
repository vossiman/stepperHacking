import json
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path

METRES_PER_MILE = 1609.344
DEFAULT_METRES_PER_STEP = 0.7


def steps_to_miles(steps: float, metres_per_step: float = DEFAULT_METRES_PER_STEP) -> float:
    return steps * metres_per_step / METRES_PER_MILE


def miles_to_steps(miles: float, metres_per_step: float = DEFAULT_METRES_PER_STEP) -> float:
    return miles * METRES_PER_MILE / metres_per_step


@dataclass(eq=False)
class Volume:
    title: str
    parts: list["Part"] = field(default_factory=list, repr=False)


@dataclass(eq=False)
class Part:
    title: str
    volume: Volume = field(repr=False)
    chapters: list["Chapter"] = field(default_factory=list, repr=False)


@dataclass(eq=False)
class Chapter:
    title: str
    leg: str
    part: Part = field(repr=False)
    waypoints: list["Waypoint"] = field(default_factory=list, repr=False)


@dataclass(eq=False)
class Waypoint:
    id: str
    name: str
    road_miles: float
    mode: str
    story: str
    walkable_miles: float
    chapter: Chapter = field(repr=False)

    @property
    def part(self) -> Part:
        return self.chapter.part

    @property
    def volume(self) -> Volume:
        return self.chapter.part.volume


@dataclass
class Position:
    reached: Waypoint
    next: "Waypoint | None"
    fraction_to_next: float
    miles_to_next: float
    chapter: Chapter
    part: Part
    chapter_fraction: float
    part_fraction: float


@dataclass(eq=False)
class Quest:
    id: str
    title: str
    ratios: dict[str, float]
    volumes: list[Volume]
    waypoints: list[Waypoint]

    def __post_init__(self) -> None:
        self._miles = [w.walkable_miles for w in self.waypoints]
        self._index = {id(w): i for i, w in enumerate(self.waypoints)}
        self._spans: dict[int, tuple[float, float]] = {}
        for volume in self.volumes:
            for part in volume.parts:
                self._add_span(part, [w for c in part.chapters for w in c.waypoints])
                for chapter in part.chapters:
                    self._add_span(chapter, chapter.waypoints)

    def _add_span(self, owner, waypoints: list[Waypoint]) -> None:
        if not waypoints:
            return
        # A span starts where the stretch into its first waypoint begins,
        # because a waypoint's mode describes the stretch ending at it.
        first = self._index[id(waypoints[0])]
        start = self.waypoints[first - 1].walkable_miles if first else 0.0
        self._spans[id(owner)] = (start, waypoints[-1].walkable_miles)

    @staticmethod
    def default_path() -> Path:
        return Path(__file__).parent / "data" / "frodo.json"

    @property
    def total_walkable_miles(self) -> float:
        return self.waypoints[-1].walkable_miles

    def position(self, walkable_miles: float) -> Position:
        x = max(0.0, walkable_miles)
        index = max(0, bisect_right(self._miles, x) - 1)
        reached = self.waypoints[index]
        if index + 1 >= len(self.waypoints):
            return Position(
                reached, None, 0.0, 0.0, reached.chapter, reached.part, 1.0, 1.0
            )
        nxt = self.waypoints[index + 1]
        segment = nxt.walkable_miles - reached.walkable_miles
        return Position(
            reached=reached,
            next=nxt,
            fraction_to_next=(x - reached.walkable_miles) / segment,
            miles_to_next=nxt.walkable_miles - x,
            chapter=nxt.chapter,
            part=nxt.part,
            chapter_fraction=self._span_fraction(nxt.chapter, x),
            part_fraction=self._span_fraction(nxt.part, x),
        )

    def _span_fraction(self, owner, x: float) -> float:
        start, end = self._spans[id(owner)]
        if end <= start:
            return 1.0
        return min(1.0, max(0.0, (x - start) / (end - start)))


def load_quest(path) -> Quest:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ratios = data["ratios"]
    volumes: list[Volume] = []
    waypoints: list[Waypoint] = []
    seen: set[str] = set()
    prev_road = None
    walkable = 0.0
    for v in data["volumes"]:
        volume = Volume(v["title"])
        volumes.append(volume)
        for p in v["parts"]:
            part = Part(p["title"], volume)
            volume.parts.append(part)
            for c in p["chapters"]:
                chapter = Chapter(c["title"], c["leg"], part)
                part.chapters.append(chapter)
                for w in c["waypoints"]:
                    wid, road, mode = w["id"], w["road_miles"], w["mode"]
                    if wid in seen:
                        raise ValueError(f"duplicate waypoint id {wid!r}")
                    seen.add(wid)
                    if mode not in ratios:
                        raise ValueError(f"unknown mode {mode!r} at {wid!r}")
                    if prev_road is not None:
                        if road < prev_road:
                            raise ValueError(
                                f"road_miles decreases at {wid!r}: {road} < {prev_road}"
                            )
                        walkable += (road - prev_road) / ratios[mode]
                    prev_road = road
                    waypoint = Waypoint(
                        wid, w["name"], road, mode, w["story"], walkable, chapter
                    )
                    chapter.waypoints.append(waypoint)
                    waypoints.append(waypoint)
    if not waypoints:
        raise ValueError("quest has no waypoints")
    return Quest(data["id"], data["title"], ratios, volumes, waypoints)
