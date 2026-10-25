"""Deterministic, offline export of a small UTC-only iCalendar subset."""

from datetime import datetime, timezone
import re
import unicodedata

__all__ = ["CalendarError", "export_calendar"]
__version__ = "0.1.0"

_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_UID = re.compile(r"[A-Za-z0-9@._-]{1,255}")
_REQUIRED = {"uid", "start", "end", "summary"}
_OPTIONAL = {"description", "location"}
_MAX_EVENTS = 10_000


class CalendarError(ValueError):
    """The input does not fit the supported calendar schema."""


def _timestamp(value: object) -> tuple[datetime, str]:
    if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
        raise CalendarError("timestamps must use YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = datetime(
            int(value[0:4]), int(value[5:7]), int(value[8:10]),
            int(value[11:13]), int(value[14:16]), int(value[17:19]),
            tzinfo=timezone.utc,
        )
    except ValueError:
        raise CalendarError("timestamps must contain a real UTC date and time") from None
    return parsed, value.replace("-", "").replace(":", "")


def _text(value: object, *, nonempty: bool = False) -> str:
    if not isinstance(value, str):
        raise CalendarError("event text must be a string")
    if nonempty and not value:
        raise CalendarError("summary must be nonempty")
    for character in value:
        category = unicodedata.category(character)
        if category == "Cs" or (category == "Cc" and character not in "\t\r\n"):
            raise CalendarError("event text contains a prohibited character")
    return (
        value.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> list[bytes]:
    """Keep each physical line within 75 bytes, counting its fold marker."""
    parts: list[bytes] = []
    current = bytearray()
    for character in line:
        encoded = character.encode("utf-8")
        if len(current) + len(encoded) > 75:
            parts.append(bytes(current))
            current = bytearray(b" ")
        current.extend(encoded)
    parts.append(bytes(current))
    return parts


def export_calendar(document: object) -> bytes:
    """Validate a calendar document and return deterministic UTF-8 ICS bytes.

    The document must be a dict with exactly ``stamp`` and ``events``. See the
    README for the deliberately small event schema. This function never mutates
    its input, reads the clock, accesses files, or performs network operations.
    """
    if not isinstance(document, dict) or document.keys() != {"stamp", "events"}:
        raise CalendarError("document must contain exactly stamp and events")
    _, stamp = _timestamp(document["stamp"])
    events = document["events"]
    if not isinstance(events, list) or len(events) > _MAX_EVENTS:
        raise CalendarError("events must be a list of at most 10000 events")

    validated: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            raise CalendarError("each event must be an object")
        keys = event.keys()
        if not _REQUIRED.issubset(keys) or not keys <= _REQUIRED | _OPTIONAL:
            raise CalendarError("event keys do not match the supported schema")
        uid = event["uid"]
        if not isinstance(uid, str) or _UID.fullmatch(uid) is None:
            raise CalendarError("uid must use 1 to 255 ASCII letters, digits, @._- only")
        if uid in seen:
            raise CalendarError("event uids must be unique")
        seen.add(uid)
        start, start_ics = _timestamp(event["start"])
        end, end_ics = _timestamp(event["end"])
        if start >= end:
            raise CalendarError("event start must precede end")
        lines = [
            "BEGIN:VEVENT",
            "UID:" + uid,
            "DTSTAMP:" + stamp,
            "DTSTART:" + start_ics,
            "DTEND:" + end_ics,
            "SUMMARY:" + _text(event["summary"], nonempty=True),
        ]
        for field in ("description", "location"):
            if field in event:
                lines.append(field.upper() + ":" + _text(event[field]))
        lines.append("END:VEVENT")
        validated.append((uid, lines))

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Lofrano Open Source//calendar-ics-export 0.1//EN",
        "CALSCALE:GREGORIAN",
    ]
    for _, event_lines in sorted(validated, key=lambda item: item[0]):
        lines.extend(event_lines)
    lines.append("END:VCALENDAR")
    physical = [part for line in lines for part in _fold(line)]
    return b"\r\n".join(physical) + b"\r\n"
