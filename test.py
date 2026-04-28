#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys

BASE_ENV = {
    "UT_LOCAL_TZ": "America/Vancouver",
    "UT_EXTRA_TZS": "UTC,America/New_York,Europe/London,Asia/Tokyo",
    "UT_NOW": "2026-03-27T12:00:00Z",
}


def run_case(input_text: str, extra_env: dict[str, str] | None = None) -> dict:
    env = os.environ.copy()
    env.update(BASE_ENV)
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        ["python3", "workflow/main.py", input_text],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return json.loads(result.stdout)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}\nExpected: {expected}\nActual:   {actual}")


def titles(result: dict) -> list[str]:
    return [item["title"] for item in result["items"]]


def find_title(result: dict, prefix: str) -> str:
    for title in titles(result):
        if title.startswith(prefix):
            return title
    raise AssertionError(f"Missing title starting with: {prefix}")


def find_item(result: dict, prefix: str) -> dict:
    for item in result["items"]:
        if item["title"].startswith(prefix):
            return item
    raise AssertionError(f"Missing item starting with: {prefix}")


def extract_iso(result: dict, prefix: str = "ISO: ") -> str:
    return find_item(result, prefix)["arg"]


def extract_epoch_seconds(result: dict, prefix: str = "Unix seconds: ") -> int:
    return int(find_item(result, prefix)["arg"])


def assert_invalid(result: dict, contains: str | None = None) -> None:
    assert_true(isinstance(result.get("items"), list), "Expected items list")
    assert_true(len(result["items"]) > 0, "Expected at least one item")

    first = result["items"][0]
    assert_true(
        first.get("valid", False) is False,
        f"Expected invalid item, got: {first}",
    )

    if contains is not None:
        subtitle = first.get("subtitle", "")
        assert_true(
            contains in subtitle,
            f'Expected subtitle containing "{contains}", got: "{subtitle}"',
        )


def test_help() -> None:
    result = run_case("")
    first = result["items"][0]
    assert_equal(first["title"], "Enter a time to convert", "wrong help title")
    assert_true(first.get("valid", False) is False, "help row should not be actionable")
    assert_true(
        "Examples:" in first.get("subtitle", ""),
        "help subtitle should include examples",
    )


def test_now() -> None:
    result = run_case("now")
    assert_equal(
        extract_iso(result), "2026-03-27T12:00:00Z", "now should use UT_NOW override"
    )


def test_now_plus_hour() -> None:
    result = run_case("now+1h")
    assert_equal(extract_iso(result), "2026-03-27T13:00:00Z", "now+1h failed")


def test_now_minus_30m() -> None:
    result = run_case("now-30m")
    assert_equal(extract_iso(result), "2026-03-27T11:30:00Z", "now-30m failed")


def test_now_compound_offset() -> None:
    result = run_case("now+1h-30m+15s")
    assert_equal(
        extract_iso(result), "2026-03-27T12:30:15Z", "compound now offset failed"
    )


def test_epoch_seconds() -> None:
    result = run_case("1711540800")
    assert_equal(extract_epoch_seconds(result), 1711540800, "epoch seconds failed")


def test_epoch_milliseconds() -> None:
    result = run_case("1711540800000")
    assert_equal(extract_epoch_seconds(result), 1711540800, "epoch milliseconds failed")


def test_iso_input() -> None:
    result = run_case("2026-03-27T12:00:00Z")
    assert_equal(extract_iso(result), "2026-03-27T12:00:00Z", "ISO round-trip failed")


def test_iso_offset_input() -> None:
    result = run_case("2026-03-27T12:00:00+09:00")
    assert_equal(
        extract_iso(result), "2026-03-27T03:00:00Z", "ISO offset conversion failed"
    )


def test_prefix_zone() -> None:
    result = run_case("utc 12:30")
    assert_equal(extract_iso(result), "2026-03-27T12:30:00Z", "prefix zone failed")


def test_suffix_zone() -> None:
    result = run_case("12:30 utc")
    assert_equal(extract_iso(result), "2026-03-27T12:30:00Z", "suffix zone failed")


def test_time_only_defaults_to_local_date() -> None:
    result = run_case("12:30")
    assert_true(
        any(title.startswith("America/Vancouver: ") for title in titles(result)),
        "missing local zone item",
    )


def test_alias_zone() -> None:
    result = run_case("tokyo 09:00")
    assert_true(
        any(title.startswith("Asia/Tokyo: ") for title in titles(result)),
        "Tokyo alias failed",
    )


def test_invalid_zone() -> None:
    result = run_case("12:30 Mars/Olympus")
    assert_invalid(result, "Could not parse input.")


def test_invalid_date() -> None:
    result = run_case("2026-99-99 12:00 utc")
    assert_invalid(result, "Could not parse input.")


def test_invalid_time() -> None:
    result = run_case("25:00 utc")
    assert_invalid(result, "Could not parse input.")


def test_date_arithmetic_iso_plus_days() -> None:
    result = run_case("2026-04-01 +7")
    assert_equal(
        extract_iso(result),
        "2026-04-08T07:00:00Z",
        "ISO date arithmetic should add days at local midnight",
    )


def test_date_arithmetic_month_name_defaults_current_year() -> None:
    result = run_case("April 1 +7")
    assert_equal(
        extract_iso(result),
        "2026-04-08T07:00:00Z",
        "month-name date arithmetic should default to current year",
    )


def test_date_arithmetic_month_name_minus_days() -> None:
    result = run_case("April 1 -7")
    assert_equal(
        extract_iso(result),
        "2026-03-25T07:00:00Z",
        "month-name date arithmetic should subtract days",
    )


def test_date_arithmetic_forced_zone_uses_zone_year() -> None:
    result = run_case(
        "April 1 +7 utc",
        {
            "UT_NOW": "2026-01-01T00:30:00Z",
            "UT_LOCAL_TZ": "America/Vancouver",
        },
    )
    assert_equal(
        extract_iso(result),
        "2026-04-08T00:00:00Z",
        "missing year should come from the forced source zone",
    )


def test_date_arithmetic_hours_with_units() -> None:
    result = run_case("2026-04-01 +8 hours")
    assert_equal(
        extract_iso(result),
        "2026-04-01T15:00:00Z",
        "explicit hour units should offset from local midnight",
    )


def test_date_arithmetic_clock_style_hours() -> None:
    result = run_case("2026-04-01 +7:30")
    assert_equal(
        extract_iso(result),
        "2026-04-01T14:30:00Z",
        "clock-style hour offsets should offset from local midnight",
    )


def test_date_arithmetic_integer_without_units_still_means_days() -> None:
    result = run_case("2026-04-01 +8")
    assert_equal(
        extract_iso(result),
        "2026-04-09T07:00:00Z",
        "bare integers should continue to mean days",
    )


def test_date_arithmetic_iso_without_spaces_works() -> None:
    result = run_case("2026-03-30+8")
    assert_equal(
        extract_iso(result),
        "2026-04-07T07:00:00Z",
        "ISO date arithmetic should allow compact operator syntax",
    )


def test_main_joins_multiple_argv_tokens() -> None:
    env = os.environ.copy()
    env.update(BASE_ENV)
    result = subprocess.run(
        ["python3", "workflow/main.py", "2026-03-30", "+", "8"],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    parsed = json.loads(result.stdout)
    assert_equal(
        extract_iso(parsed),
        "2026-04-07T07:00:00Z",
        "main should join multiple argv tokens into one query",
    )


def test_duplicate_configured_zones_deduped() -> None:
    result = run_case(
        "now",
        {
            "UT_LOCAL_TZ": "America/Vancouver",
            "UT_EXTRA_TZS": "UTC,UTC,America/Vancouver,Asia/Tokyo",
        },
    )

    all_titles = titles(result)

    assert_equal(
        sum(title.startswith("America/Vancouver: ") for title in all_titles),
        1,
        "Vancouver should appear once",
    )
    assert_equal(
        sum(title.startswith("UTC: ") for title in all_titles),
        1,
        "UTC should appear once",
    )
    assert_equal(
        sum(title.startswith("Asia/Tokyo: ") for title in all_titles),
        1,
        "Tokyo should appear once",
    )


def test_modifier_copy_targets() -> None:
    result = run_case("now")
    item = find_item(result, "America/Vancouver: ")
    assert_equal(
        item["mods"]["cmd"]["arg"], "2026-03-27T12:00:00Z", "cmd should copy ISO"
    )
    assert_equal(
        item["mods"]["alt"]["arg"], "1774612800", "alt should copy Unix seconds"
    )


def test_dst_nonexistent_rejected() -> None:
    result = run_case("2026-03-08 02:30 America/Vancouver")
    assert_invalid(result, "Nonexistent local time")


def test_dst_ambiguous_returns_two_occurrences() -> None:
    result = run_case("2026-11-01 01:30 America/Vancouver")
    assert_equal(
        extract_iso(result, "Earlier occurrence · ISO: "),
        "2026-11-01T08:30:00Z",
        "earlier occurrence failed",
    )
    assert_equal(
        extract_iso(result, "Later occurrence · ISO: "),
        "2026-11-01T09:30:00Z",
        "later occurrence failed",
    )


def test_dst_unambiguous_before_fall_back() -> None:
    result = run_case("2026-11-01 00:30 America/Vancouver")
    assert_equal(extract_iso(result), "2026-11-01T07:30:00Z", "before fall-back failed")


def test_dst_unambiguous_after_fall_back() -> None:
    result = run_case("2026-11-01 03:30 America/Vancouver")
    assert_equal(extract_iso(result), "2026-11-01T11:30:00Z", "after fall-back failed")


def test_now_with_zone_token_still_works() -> None:
    result = run_case("utc now+1h")
    assert_equal(
        extract_iso(result),
        "2026-03-27T13:00:00Z",
        "forced token with now offset failed",
    )


def test_result_shape() -> None:
    result = run_case("now")
    assert_true(isinstance(result["items"], list), "items must be a list")
    for item in result["items"]:
        assert_true(isinstance(item["title"], str), "title must be a string")
        if "subtitle" in item:
            assert_true(isinstance(item["subtitle"], str), "subtitle must be a string")
        if "arg" in item:
            assert_true(isinstance(item["arg"], str), "arg must be a string")


def test_tomorrow_9am() -> None:
    result = run_case("tomorrow 9am")
    assert_equal(extract_iso(result), "2026-03-28T16:00:00Z", "tomorrow parsing failed")


def test_today_9am() -> None:
    result = run_case("today 9am")
    assert_equal(extract_iso(result), "2026-03-27T16:00:00Z", "today parsing failed")


def test_yesterday_9am() -> None:
    result = run_case("yesterday 9am")
    assert_equal(
        extract_iso(result), "2026-03-26T16:00:00Z", "yesterday parsing failed"
    )


def test_in_3_hours() -> None:
    result = run_case("in 3 hours")
    assert_equal(
        extract_iso(result), "2026-03-27T15:00:00Z", "in 3 hours parsing failed"
    )


def test_in_90_minutes() -> None:
    result = run_case("in 90 minutes")
    assert_equal(
        extract_iso(result), "2026-03-27T13:30:00Z", "in 90 minutes parsing failed"
    )


def test_next_week_9am() -> None:
    result = run_case("next week 9am")
    assert_equal(
        extract_iso(result), "2026-04-03T16:00:00Z", "next week parsing failed"
    )


def test_true_abbreviation_suffix() -> None:
    result = run_case("9am PST")
    assert_equal(
        extract_iso(result), "2026-03-27T16:00:00Z", "PST suffix parsing failed"
    )


def test_true_abbreviation_prefix() -> None:
    result = run_case("PST 9am")
    assert_equal(
        extract_iso(result), "2026-03-27T16:00:00Z", "PST prefix parsing failed"
    )


def test_discord_utility_item() -> None:
    result = run_case("now")
    item = find_item(result, "Discord timestamp: ")
    assert_equal(item["arg"], "<t:1774612800:f>", "Discord timestamp failed")


def test_rfc3339_utility_item() -> None:
    result = run_case("now")
    item = find_item(result, "RFC 3339: ")
    assert_equal(item["arg"], "2026-03-27T12:00:00Z", "RFC 3339 failed")


def test_compact_modifier() -> None:
    result = run_case("now")
    item = find_item(result, "America/Vancouver: ")
    assert_true("alt+shift" in item["mods"], "missing compact modifier")


def test_ctrl_modifier() -> None:
    result = run_case("now")
    item = find_item(result, "America/Vancouver: ")
    assert_true(
        item["mods"]["ctrl"]["arg"].endswith("UTC"), "ctrl should copy UTC formatted"
    )


def test_shift_modifier() -> None:
    result = run_case("now")
    item = find_item(result, "Asia/Tokyo: ")
    assert_true(
        item["mods"]["shift"]["arg"].endswith("PDT"),
        "shift should copy configured local formatted",
    )


def test_empty_extra_timezones_skipped() -> None:
    result = run_case(
        "now",
        {
            "UT_LOCAL_TZ": "America/Vancouver",
            "UT_EXTRA_TZS": " , ,UTC,   ,",
        },
    )

    all_titles = titles(result)

    assert_equal(
        sum(title.startswith("America/Vancouver: ") for title in all_titles),
        1,
        "Local timezone should appear once",
    )

    assert_equal(
        sum(title.startswith("UTC: ") for title in all_titles),
        1,
        "UTC should appear once",
    )

    assert_true(
        not any(title.startswith("Asia/Tokyo: ") for title in all_titles),
        "Tokyo should not appear when not configured",
    )


def test_invalid_extra_timezones_skipped() -> None:
    result = run_case(
        "now",
        {
            "UT_EXTRA_TZS": "UTC,Not/AZone,Asia/Tokyo,Mars/Olympus",
        },
    )

    all_titles = titles(result)

    assert_equal(
        sum(title.startswith("UTC: ") for title in all_titles),
        1,
        "UTC should appear once",
    )
    assert_equal(
        sum(title.startswith("Asia/Tokyo: ") for title in all_titles),
        1,
        "Tokyo should appear once",
    )

    assert_true(
        not any(title.startswith("Not/AZone: ") for title in all_titles),
        "Invalid timezone should be skipped",
    )
    assert_true(
        not any(title.startswith("Mars/Olympus: ") for title in all_titles),
        "Invalid timezone should be skipped",
    )


def test_csv_extra_timezones_override_legacy() -> None:
    result = run_case(
        "now",
        {
            "UT_EXTRA_TZS": "UTC,Asia/Tokyo",
            "UT_TZ1": "America/New_York",  # should be ignored
            "UT_TZ2": "Europe/London",
        },
    )

    all_titles = titles(result)

    assert_equal(
        sum(title.startswith("UTC: ") for title in all_titles),
        1,
        "UTC should appear once",
    )
    assert_equal(
        sum(title.startswith("Asia/Tokyo: ") for title in all_titles),
        1,
        "Tokyo should appear once",
    )

    assert_true(
        not any(title.startswith("America/New_York: ") for title in all_titles),
        "Legacy zones should be ignored",
    )

def test_now_plus_hour_with_spaces() -> None:
    result = run_case("now + 1h")
    assert_equal(extract_iso(result), "2026-03-27T13:00:00Z", "now + 1h failed")

def test_now_compound_offset_with_spaces() -> None:
    result = run_case("now + 1h - 30m + 15s")
    assert_equal(
        extract_iso(result),
        "2026-03-27T12:30:15Z",
        "compound spaced now offset failed",
    )


def main() -> None:
    tests = [
        ("help", test_help),
        ("now", test_now),
        ("now+1h", test_now_plus_hour),
        ("now-30m", test_now_minus_30m),
        ("compound now offset", test_now_compound_offset),
        ("epoch seconds", test_epoch_seconds),
        ("epoch milliseconds", test_epoch_milliseconds),
        ("iso input", test_iso_input),
        ("iso offset input", test_iso_offset_input),
        ("prefix zone", test_prefix_zone),
        ("suffix zone", test_suffix_zone),
        ("time only default date", test_time_only_defaults_to_local_date),
        ("alias zone", test_alias_zone),
        ("invalid zone", test_invalid_zone),
        ("invalid date", test_invalid_date),
        ("invalid time", test_invalid_time),
        ("date arithmetic iso plus days", test_date_arithmetic_iso_plus_days),
        (
            "date arithmetic month name defaults current year",
            test_date_arithmetic_month_name_defaults_current_year,
        ),
        ("date arithmetic month name minus days", test_date_arithmetic_month_name_minus_days),
        (
            "date arithmetic forced zone uses zone year",
            test_date_arithmetic_forced_zone_uses_zone_year,
        ),
        ("date arithmetic hours with units", test_date_arithmetic_hours_with_units),
        ("date arithmetic clock style hours", test_date_arithmetic_clock_style_hours),
        (
            "date arithmetic integer without units means days",
            test_date_arithmetic_integer_without_units_still_means_days,
        ),
        (
            "date arithmetic iso without spaces works",
            test_date_arithmetic_iso_without_spaces_works,
        ),
        ("main joins multiple argv tokens", test_main_joins_multiple_argv_tokens),
        ("configured zone dedupe", test_duplicate_configured_zones_deduped),
        ("modifier copy targets", test_modifier_copy_targets),
        ("dst nonexistent rejected", test_dst_nonexistent_rejected),
        ("dst ambiguous returns two", test_dst_ambiguous_returns_two_occurrences),
        ("dst before fallback", test_dst_unambiguous_before_fall_back),
        ("dst after fallback", test_dst_unambiguous_after_fall_back),
        ("now with zone token", test_now_with_zone_token_still_works),
        ("result shape", test_result_shape),
        ("tomorrow 9am", test_tomorrow_9am),
        ("today 9am", test_today_9am),
        ("yesterday 9am", test_yesterday_9am),
        ("in 3 hours", test_in_3_hours),
        ("in 90 minutes", test_in_90_minutes),
        ("next week 9am", test_next_week_9am),
        ("true abbreviation suffix", test_true_abbreviation_suffix),
        ("true abbreviation prefix", test_true_abbreviation_prefix),
        ("discord utility item", test_discord_utility_item),
        ("rfc3339 utility item", test_rfc3339_utility_item),
        ("compact modifier", test_compact_modifier),
        ("ctrl modifier", test_ctrl_modifier),
        ("shift modifier", test_shift_modifier),
        ("empty extra zones skipped", test_empty_extra_timezones_skipped),
        ("invalid extra zones skipped", test_invalid_extra_timezones_skipped),
        ("csv extra zones override legacy", test_csv_extra_timezones_override_legacy),
        ("now + 1h", test_now_plus_hour_with_spaces),
        ("compound spaced now offset", test_now_compound_offset_with_spaces),
    ]

    for name, fn in tests:
        fn()
        print(f"✅ {name}")

    print("\n🎉 All tests passed")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"❌ {exc}")
        sys.exit(1)
