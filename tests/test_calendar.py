"""Behavioral tests with synthetic inputs and independently specified output."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from calendar_ics_export import CalendarError, export_calendar

ROOT = Path(__file__).resolve().parents[1]
STAMP = "2026-10-25T12:00:00Z"


def event(**changes):
    value = {
        "uid": "demo@example.invalid",
        "start": "2026-11-03T14:00:00Z",
        "end": "2026-11-03T15:00:00Z",
        "summary": "Map workshop",
    }
    value.update(changes)
    return value


def document(*events):
    return {"stamp": STAMP, "events": list(events)}


def unfold(output):
    return output.replace(b"\r\n ", b"")


class ExportTests(unittest.TestCase):
    def test_exact_single_event_output(self):
        expected = (
            b"BEGIN:VCALENDAR\r\n"
            b"VERSION:2.0\r\n"
            b"PRODID:-//Lofrano Open Source//calendar-ics-export 0.1//EN\r\n"
            b"CALSCALE:GREGORIAN\r\n"
            b"BEGIN:VEVENT\r\n"
            b"UID:demo@example.invalid\r\n"
            b"DTSTAMP:20261025T120000Z\r\n"
            b"DTSTART:20261103T140000Z\r\n"
            b"DTEND:20261103T150000Z\r\n"
            b"SUMMARY:Map workshop\r\n"
            b"END:VEVENT\r\n"
            b"END:VCALENDAR\r\n"
        )
        self.assertEqual(export_calendar(document(event())), expected)

    def test_empty_calendar_has_only_fixed_header_and_footer(self):
        self.assertEqual(
            export_calendar(document()),
            b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
            b"PRODID:-//Lofrano Open Source//calendar-ics-export 0.1//EN\r\n"
            b"CALSCALE:GREGORIAN\r\nEND:VCALENDAR\r\n",
        )

    def test_events_sorted_by_ascii_uid(self):
        value = export_calendar(document(event(uid="z"), event(uid="a"), event(uid="A")))
        self.assertLess(value.index(b"UID:A\r\n"), value.index(b"UID:a\r\n"))
        self.assertLess(value.index(b"UID:a\r\n"), value.index(b"UID:z\r\n"))

    def test_input_order_does_not_change_bytes(self):
        first, second = event(uid="b"), event(uid="a")
        self.assertEqual(
            export_calendar(document(first, second)),
            export_calendar(document(second, first)),
        )

    def test_input_and_key_order_do_not_change_bytes(self):
        original = event(description="notes", location="room")
        reversed_keys = dict(reversed(list(original.items())))
        self.assertEqual(
            export_calendar(document(original)), export_calendar(document(reversed_keys))
        )

    def test_input_is_not_mutated(self):
        source = document(event(uid="b"), event(uid="a", summary="one\r\ntwo"))
        snapshot = copy.deepcopy(source)
        export_calendar(source)
        self.assertEqual(source, snapshot)

    def test_global_stamp_is_reused_without_consulting_current_time(self):
        source = document(event(uid="a"), event(uid="b"))
        source["stamp"] = "2001-02-03T04:05:06Z"
        value = export_calendar(source)
        self.assertEqual(value.count(b"DTSTAMP:20010203T040506Z\r\n"), 2)
        self.assertEqual(value, export_calendar(source))

    def test_optional_fields_have_fixed_order(self):
        value = export_calendar(document(event(location="Room", description="Notes")))
        self.assertIn(b"SUMMARY:Map workshop\r\nDESCRIPTION:Notes\r\nLOCATION:Room\r\n", value)

    def test_empty_optional_fields_are_retained(self):
        value = export_calendar(document(event(description="", location="")))
        self.assertIn(b"DESCRIPTION:\r\nLOCATION:\r\n", value)

    def test_absent_optional_fields_are_omitted(self):
        value = export_calendar(document(event()))
        self.assertNotIn(b"DESCRIPTION:", value)
        self.assertNotIn(b"LOCATION:", value)

    def test_text_escaping(self):
        value = export_calendar(document(event(summary="A\\B;C,D: E")))
        self.assertIn(b"SUMMARY:A\\\\B\\;C\\,D: E\r\n", value)

    def test_all_newline_forms_are_normalized_and_escaped(self):
        value = export_calendar(document(event(summary="a\r\nb\rc\nd")))
        self.assertIn(b"SUMMARY:a\\nb\\nc\\nd\r\n", value)

    def test_text_escape_applies_to_all_text_properties(self):
        value = export_calendar(document(event(summary="a,b", description="c;d", location="e\\f")))
        self.assertIn(b"SUMMARY:a\\,b\r\nDESCRIPTION:c\\;d\r\nLOCATION:e\\\\f\r\n", value)

    def test_allowed_tab_and_unicode_are_preserved(self):
        value = export_calendar(document(event(summary="Café\t地图 🗺")))
        self.assertIn("SUMMARY:Café\t地图 🗺\r\n".encode("utf-8"), value)

    def test_newlines_cannot_inject_properties_or_components(self):
        attack = "Demo\r\nEND:VEVENT\r\nBEGIN:VEVENT\nATTENDEE:secret"
        value = export_calendar(document(event(summary=attack, description=attack, location=attack)))
        self.assertEqual(value.count(b"BEGIN:VEVENT\r\n"), 1)
        self.assertEqual(value.count(b"END:VEVENT\r\n"), 1)
        self.assertNotIn(b"\r\nATTENDEE:", value)
        self.assertIn(b"\\nEND:VEVENT\\nBEGIN:VEVENT\\nATTENDEE:secret", unfold(value))

    def test_all_output_newlines_are_crlf_and_final_newline_exists(self):
        value = export_calendar(document(event(summary="one\ntwo")))
        self.assertTrue(value.endswith(b"\r\n"))
        without_crlf = value.replace(b"\r\n", b"")
        self.assertNotIn(b"\n", without_crlf)
        self.assertNotIn(b"\r", without_crlf)

    def test_exact_75_byte_line_is_not_folded(self):
        value = export_calendar(document(event(summary="x" * 67)))
        self.assertIn(b"SUMMARY:" + b"x" * 67 + b"\r\nEND:VEVENT", value)

    def test_76_byte_line_is_folded_with_one_continuation_space(self):
        value = export_calendar(document(event(summary="x" * 68)))
        self.assertIn(b"SUMMARY:" + b"x" * 67 + b"\r\n x\r\n", value)

    def test_each_continuation_space_counts_against_75_bytes(self):
        value = export_calendar(document(event(summary="x" * 300)))
        summary_lines = value[value.index(b"SUMMARY:"):value.index(b"END:VEVENT")].split(b"\r\n")[:-1]
        self.assertEqual([len(line) for line in summary_lines], [75, 75, 75, 75, 12])
        self.assertTrue(all(line.startswith(b" ") for line in summary_lines[1:]))
        self.assertIn(b"SUMMARY:" + b"x" * 300 + b"\r\n", unfold(value))

    def test_multibyte_folds_keep_every_physical_line_valid_utf8(self):
        summary = "é地图🗺" * 100
        value = export_calendar(document(event(summary=summary)))
        for line in value.split(b"\r\n"):
            self.assertLessEqual(len(line), 75)
            line.decode("utf-8")
        self.assertIn(("SUMMARY:" + summary + "\r\n").encode("utf-8"), unfold(value))

    def test_four_byte_character_does_not_split_at_boundary(self):
        value = export_calendar(document(event(summary="x" * 66 + "🗺end")))
        self.assertIn(b"SUMMARY:" + b"x" * 66 + "\r\n 🗺end\r\n".encode("utf-8"), value)

    def test_long_uid_is_folded_without_changing_value(self):
        value = export_calendar(document(event(uid="a" * 255)))
        self.assertIn(b"UID:" + b"a" * 255 + b"\r\n", unfold(value))
        self.assertTrue(all(len(line) <= 75 for line in value.split(b"\r\n")))


class ValidationTests(unittest.TestCase):
    def assert_invalid(self, source):
        with self.assertRaises(CalendarError):
            export_calendar(source)

    def test_document_must_be_an_object(self):
        for value in (None, [], "calendar", 42, True):
            with self.subTest(value=value):
                self.assert_invalid(value)

    def test_document_keys_are_exact(self):
        for value in ({}, {"stamp": STAMP}, {"events": []}, {"stamp": STAMP, "events": [], "extra": 1}):
            with self.subTest(value=value):
                self.assert_invalid(value)

    def test_events_must_be_a_list(self):
        for value in (None, {}, (), "", 1):
            with self.subTest(value=value):
                self.assert_invalid({"stamp": STAMP, "events": value})

    def test_event_must_be_an_object(self):
        for value in (None, [], "event", True):
            with self.subTest(value=value):
                self.assert_invalid(document(value))

    def test_required_event_keys_cannot_be_missing(self):
        for key in ("uid", "start", "end", "summary"):
            source = event()
            del source[key]
            with self.subTest(key=key):
                self.assert_invalid(document(source))

    def test_unknown_event_fields_are_rejected(self):
        for key in ("rrule", "attendees", "timezone", "Summary", "extra"):
            with self.subTest(key=key):
                self.assert_invalid(document(event(**{key: "value"})))

    def test_uid_character_set_and_length_are_strict(self):
        for uid in ("", "a" * 256, "x y", "café", "x:y", "x/y", "x;VALUE=URI", "x\r\nBEGIN:VEVENT", None, 1):
            with self.subTest(uid=uid):
                self.assert_invalid(document(event(uid=uid)))

    def test_uid_punctuation_and_case_are_supported(self):
        self.assertIsInstance(export_calendar(document(event(uid="A-z_09.@"))), bytes)
        self.assertIsInstance(export_calendar(document(event(uid="A"), event(uid="a"))), bytes)

    def test_duplicate_uid_is_rejected(self):
        self.assert_invalid(document(event(), event(summary="Another event")))

    def test_timestamps_reject_offsets_fractions_and_alternate_formats(self):
        invalid = (
            "2026-11-03", "20261103T140000Z", "2026-11-03T14:00:00+00:00",
            "2026-11-03T14:00:00.000Z", "2026-11-03t14:00:00Z",
            "2026-11-03T14:00:00z", "2026-11-03 14:00:00Z", "2026-11-03T14:00Z",
            "2026-11-03T14:00:00Z\n", "２０２６-11-03T14:00:00Z", None, 1,
        )
        for value in invalid:
            for key in ("stamp", "start", "end"):
                source = document(event())
                if key == "stamp":
                    source[key] = value
                else:
                    source["events"][0][key] = value
                with self.subTest(value=value, key=key):
                    self.assert_invalid(source)

    def test_timestamps_reject_impossible_dates_and_times(self):
        for value in (
            "0000-01-01T00:00:00Z", "2025-02-29T00:00:00Z", "2026-04-31T00:00:00Z",
            "2026-13-01T00:00:00Z", "2026-01-00T00:00:00Z", "2026-01-01T24:00:00Z",
            "2026-01-01T00:60:00Z", "2026-01-01T00:00:60Z",
        ):
            with self.subTest(value=value):
                self.assert_invalid({"stamp": value, "events": []})

    def test_valid_leap_day_and_year_boundaries(self):
        source = document(event(start="2024-02-29T23:59:59Z", end="2024-03-01T00:00:00Z"))
        source["stamp"] = "0001-01-01T00:00:00Z"
        self.assertIn(b"DTSTAMP:00010101T000000Z", export_calendar(source))
        source["stamp"] = "9999-12-31T23:59:59Z"
        self.assertIn(b"DTSTAMP:99991231T235959Z", export_calendar(source))

    def test_end_must_strictly_follow_start(self):
        for end in ("2026-11-03T14:00:00Z", "2026-11-03T13:59:59Z"):
            with self.subTest(end=end):
                self.assert_invalid(document(event(end=end)))

    def test_one_second_event_and_cross_year_event_are_valid(self):
        self.assertIsInstance(export_calendar(document(event(end="2026-11-03T14:00:01Z"))), bytes)
        self.assertIsInstance(export_calendar(document(event(start="2026-12-31T23:59:59Z", end="2027-01-01T00:00:00Z"))), bytes)

    def test_summary_must_be_a_nonempty_string(self):
        for value in ("", None, 0, False, [], {}):
            with self.subTest(value=value):
                self.assert_invalid(document(event(summary=value)))

    def test_whitespace_only_summary_is_a_nonempty_string(self):
        self.assertIn(b"SUMMARY: \t\r\n", export_calendar(document(event(summary=" \t"))))

    def test_optional_text_requires_strings(self):
        for key in ("description", "location"):
            for value in (None, 1, False, [], {}):
                with self.subTest(key=key, value=value):
                    self.assert_invalid(document(event(**{key: value})))

    def test_c0_and_c1_control_characters_are_rejected_in_all_text(self):
        controls = [chr(n) for n in range(0xA0) if n < 0x20 or n >= 0x7F]
        for character in controls:
            if character in "\t\r\n":
                continue
            for key in ("summary", "description", "location"):
                with self.subTest(codepoint=ord(character), key=key):
                    self.assert_invalid(document(event(**{key: "a" + character + "b"})))

    def test_surrogates_are_rejected_in_all_text(self):
        for character in ("\ud800", "\udfff"):
            for key in ("summary", "description", "location"):
                with self.subTest(codepoint=ord(character), key=key):
                    self.assert_invalid(document(event(**{key: character})))

    def test_ten_thousand_events_are_accepted(self):
        value = export_calendar(document(*(event(uid=f"event-{i}") for i in range(10_000))))
        self.assertEqual(value.count(b"BEGIN:VEVENT\r\n"), 10_000)

    def test_more_than_ten_thousand_events_are_rejected(self):
        self.assert_invalid(document(*([event()] * 10_001)))

    def test_rejected_input_is_not_mutated(self):
        source = document(event(uid="z"), event(uid="a", summary="\x00"))
        snapshot = copy.deepcopy(source)
        self.assert_invalid(source)
        self.assertEqual(source, snapshot)


class CliTests(unittest.TestCase):
    def run_cli(self, *arguments, payload=None):
        return subprocess.run(
            [sys.executable, "-m", "calendar_ics_export", *arguments],
            input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=ROOT, check=False,
        )

    def assert_failure(self, result):
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertTrue(result.stderr.startswith(b"calendar-ics-export: "))
        self.assertNotIn(b"Traceback", result.stderr)

    def test_explicit_stdin_produces_api_bytes(self):
        source = document(event(summary="Café"))
        result = self.run_cli("-", payload=json.dumps(source, ensure_ascii=False).encode("utf-8"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(result.stdout, export_calendar(source))

    def test_file_input_produces_api_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "synthetic.json")
            path.write_text(json.dumps(document(event())), encoding="utf-8")
            result = self.run_cli(str(path))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(result.stdout, export_calendar(document(event())))

    def test_example_is_valid_and_sorts_events(self):
        result = self.run_cli(str(ROOT / "examples" / "workshop.json"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertLess(result.stdout.index(b"UID:workshop-01"), result.stdout.index(b"UID:workshop-02"))

    def test_input_argument_is_required(self):
        self.assert_failure(self.run_cli())

    def test_argument_errors_do_not_echo_content_or_paths(self):
        result = self.run_cli("--private-SYNTHETIC_SECRET", "/synthetic/private/path")
        self.assert_failure(result)
        self.assertNotIn(b"SYNTHETIC_SECRET", result.stderr)
        self.assertNotIn(b"/synthetic", result.stderr)

    def test_unreadable_path_is_sanitized(self):
        result = self.run_cli("/no-such-calendar-SYNTHETIC_SECRET/input.json")
        self.assert_failure(result)
        self.assertNotIn(b"SYNTHETIC_SECRET", result.stderr)
        self.assertNotIn(b"input.json", result.stderr)

    def test_malformed_json_is_sanitized(self):
        result = self.run_cli("-", payload=b'{"SYNTHETIC_SECRET": broken}')
        self.assert_failure(result)
        self.assertNotIn(b"SYNTHETIC_SECRET", result.stderr)

    def test_invalid_utf8_is_rejected(self):
        self.assert_failure(self.run_cli("-", payload=b"\xff"))

    def test_duplicate_top_level_key_is_rejected(self):
        payload = ('{"stamp":"' + STAMP + '","events":[],"events":[]}').encode()
        result = self.run_cli("-", payload=payload)
        self.assert_failure(result)
        self.assertIn(b"duplicate keys", result.stderr)

    def test_duplicate_nested_key_is_rejected(self):
        raw_event = json.dumps(event()).replace('"Map workshop"', '"Map workshop", "summary":"SYNTHETIC_SECRET"')
        payload = ('{"stamp":"' + STAMP + '","events":[' + raw_event + ']}').encode()
        result = self.run_cli("-", payload=payload)
        self.assert_failure(result)
        self.assertIn(b"duplicate keys", result.stderr)
        self.assertNotIn(b"SYNTHETIC_SECRET", result.stderr)

    def test_nonfinite_constants_are_rejected(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            payload = ('{"stamp":"' + STAMP + '","events":' + constant + '}').encode()
            with self.subTest(constant=constant):
                result = self.run_cli("-", payload=payload)
                self.assert_failure(result)
                self.assertIn(b"nonfinite constant", result.stderr)

    def test_number_overflow_cannot_reach_valid_output(self):
        raw_event = json.dumps(event()).replace('"Map workshop"', '1e10000')
        payload = ('{"stamp":"' + STAMP + '","events":[' + raw_event + ']}').encode()
        self.assert_failure(self.run_cli("-", payload=payload))

    def test_exactly_four_mib_input_is_accepted(self):
        payload = json.dumps(document()).encode()
        payload += b" " * (4 * 1024 * 1024 - len(payload))
        result = self.run_cli("-", payload=payload)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, export_calendar(document()))

    def test_input_over_four_mib_is_rejected(self):
        result = self.run_cli("-", payload=b" " * (4 * 1024 * 1024 + 1))
        self.assert_failure(result)
        self.assertIn(b"4 MiB", result.stderr)

    def test_invalid_later_event_never_emits_partial_calendar(self):
        source = document(event(uid="valid"), event(uid="invalid", summary=""))
        self.assert_failure(self.run_cli("-", payload=json.dumps(source).encode()))

    def test_escaped_json_surrogate_is_rejected_without_traceback(self):
        self.assert_failure(self.run_cli("-", payload=json.dumps(document(event(summary="\ud800"))).encode()))

    def test_excessive_json_nesting_is_rejected_without_traceback(self):
        self.assert_failure(self.run_cli("-", payload=b"[" * 2000 + b"0" + b"]" * 2000))

    def test_closed_output_pipe_exits_cleanly_with_sanitized_error(self):
        with subprocess.Popen(
            [sys.executable, "-m", "calendar_ics_export", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=ROOT,
        ) as process:
            process.stdout.close()
            process.stdin.write(json.dumps(document(event())).encode())
            process.stdin.close()
            error = process.stderr.read()
            self.assertEqual(process.wait(), 2)
        self.assertEqual(error, b"calendar-ics-export: unable to write output\n")

    def test_help_is_available_without_input(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"UTC-only", result.stdout)
        self.assertEqual(result.stderr, b"")

    def test_version_is_available_without_input(self):
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"0.1.0\n")


if __name__ == "__main__":
    unittest.main()
