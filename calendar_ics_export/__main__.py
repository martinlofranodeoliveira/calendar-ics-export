"""Command-line interface for calendar_ics_export."""

import argparse
import json
import sys
from collections.abc import Sequence

from . import CalendarError, __version__, export_calendar

_MAX_INPUT_BYTES = 4 * 1024 * 1024
_PREFIX = "calendar-ics-export: "


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's default error can echo arbitrary arguments and file paths.
        self.exit(2, _PREFIX + "invalid arguments; use --help\n")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CalendarError("JSON contains duplicate keys")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise CalendarError("JSON contains a nonfinite constant")


def _read_document(source: str) -> object:
    try:
        if source == "-":
            raw = sys.stdin.buffer.read(_MAX_INPUT_BYTES + 1)
        else:
            with open(source, "rb") as stream:
                raw = stream.read(_MAX_INPUT_BYTES + 1)
    except OSError:
        raise CalendarError("unable to read input") from None
    if len(raw) > _MAX_INPUT_BYTES:
        raise CalendarError("input exceeds the 4 MiB limit")
    try:
        decoded = raw.decode("utf-8")
        return json.loads(
            decoded, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        if isinstance(error, CalendarError):
            raise
        raise CalendarError("input must be valid UTF-8 JSON") from None


def main(argv: Sequence[str] | None = None) -> int:
    parser = _Parser(
        prog="calendar-ics-export",
        description="Export a validated UTC-only JSON calendar as ICS to stdout.",
    )
    parser.add_argument("input", help="UTF-8 JSON file, or - to read stdin (maximum 4 MiB)")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        output = export_calendar(_read_document(args.input))
    except CalendarError as error:
        sys.stderr.write(_PREFIX + str(error) + "\n")
        return 2
    try:
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
    except OSError:
        # Discard any pending buffered bytes so interpreter shutdown cannot
        # retry a failed pipe flush and print an unsanitized traceback.
        try:
            sys.stdout.close()
        except OSError:
            pass
        sys.stderr.write(_PREFIX + "unable to write output\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
