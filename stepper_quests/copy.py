"""Toast and tooltip wording, kept free of Qt so it can be unit tested."""

from .counter import Session
from .quests import Position, miles_to_steps


def format_steps(steps: float) -> str:
    return f"{round(steps):,}"


def _steps_to_next(position: Position, metres_per_step: float) -> str:
    return format_steps(miles_to_steps(position.miles_to_next, metres_per_step))


def start_message(position: Position, metres_per_step: float) -> str:
    leaving = f"Leaving {position.reached.name}."
    if position.next is None:
        return f"{leaving} The road ends here."
    return f"{leaving} {_steps_to_next(position, metres_per_step)} steps to {position.next.name}."


def end_message(session: Session, position: Position, metres_per_step: float) -> str:
    end = session.end if session.end is not None else session.start
    minutes = max(1, round((end - session.start) / 60))
    walked = f"{format_steps(session.steps)} steps in {minutes} min."
    if position.next is None:
        return f"{walked} The road ends at {position.reached.name}."
    return (
        f"{walked} {position.next.name} is "
        f"{_steps_to_next(position, metres_per_step)} steps away."
    )


def tooltip(state: str, spm: int, today_steps: float) -> str:
    if state == "unconfigured":
        return "no stepper MAC set, see Settings..."
    if state == "reconnecting":
        return "reconnecting"
    if state == "stepping":
        return f"stepping, {spm} spm, {format_steps(today_steps)} today"
    return f"{state}, {format_steps(today_steps)} today"
