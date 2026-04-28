#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class InstantCandidate:
    instant_utc: datetime
    label: str = ""

    def __post_init__(self) -> None:
        if self.instant_utc.tzinfo is None:
            raise ValueError("InstantCandidate.instant_utc must be timezone-aware")
        if self.instant_utc.utcoffset() != timedelta(0):
            raise ValueError("InstantCandidate.instant_utc must be UTC")


@dataclass(frozen=True)
class ParsedInstant:
    candidates: list[InstantCandidate]
    interpretation: str
    parser_name: str


@dataclass(frozen=True)
class ParseErrorResult:
    message: str


@dataclass(frozen=True)
class HelpResult:
    pass


ParseResult = ParsedInstant | ParseErrorResult | HelpResult


@dataclass(frozen=True)
class ParseContext:
    raw_text: str
    trimmed: str
    forced_zone: str | None
    body: str
    source_zone: str


@dataclass(frozen=True)
class ParseAttempt:
    handled: bool
    result: ParseResult | None = None


ParserFn = Callable[[ParseContext], ParseAttempt]


def ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("Expected timezone-aware datetime")
    return dt


def ensure_utc(dt: datetime) -> datetime:
    aware = ensure_aware(dt)
    utc_dt = aware.astimezone(UTC).replace(microsecond=0)
    return ensure_aware(utc_dt)


def env_flag(name: str, default: bool = False) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def env_str(name: str, default: str) -> str:
    value = (os.getenv(name) or "").strip()
    return value or default


def get_system_timezone() -> str:
    local_now = ensure_aware(datetime.now().astimezone())
    tz = local_now.tzinfo
    if tz is None:
        return "UTC"

    key = getattr(tz, "key", None)
    if isinstance(key, str) and key:
        return key

    name = tz.tzname(local_now)
    if isinstance(name, str) and "/" in name:
        return name

    return "UTC"


SYSTEM_TIMEZONE = get_system_timezone()
CONFIGURED_LOCAL_TZ = (os.getenv("UT_LOCAL_TZ") or "").strip() or SYSTEM_TIMEZONE


def parse_extra_output_zones() -> list[str]:
    csv_value = (os.getenv("UT_EXTRA_TZS") or "").strip()

    if csv_value:
        return [zone.strip() for zone in csv_value.split(",") if zone.strip()]

    legacy_values = [
        (os.getenv("UT_TZ1") or "").strip(),
        (os.getenv("UT_TZ2") or "").strip(),
        (os.getenv("UT_TZ3") or "").strip(),
        (os.getenv("UT_TZ4") or "").strip(),
    ]
    return [zone for zone in legacy_values if zone]


OUTPUT_ZONES_RAW = parse_extra_output_zones()

USE_12H = env_flag("UT_USE_12H", default=False)
DATE_FORMAT = env_str("UT_DATE_FORMAT", "%Y-%m-%d")
COMPACT_DATE_FORMAT = env_str("UT_COMPACT_DATE_FORMAT", "%Y-%m-%d")
MARKDOWN_DATE_FORMAT = env_str("UT_MARKDOWN_DATE_FORMAT", "%Y-%m-%d %H:%M")
DISCORD_STYLE = env_str("UT_DISCORD_STYLE", "f")
DEBUG_MODE = env_flag("UT_DEBUG", default=False)

ZONE_ALIASES = {
    "utc": "UTC",
    "z": "UTC",
    "gmt": "UTC",
    "local": CONFIGURED_LOCAL_TZ,
    "system": SYSTEM_TIMEZONE,
    "vancouver": "America/Vancouver",
    "pt": "America/Vancouver",
    "pst": "America/Vancouver",
    "pdt": "America/Vancouver",
    "mountain": "America/Denver",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "central": "America/Chicago",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "eastern": "America/New_York",
    "est": "America/New_York",
    "edt": "America/New_York",
    "london": "Europe/London",
    "uk": "Europe/London",
    "tokyo": "Asia/Tokyo",
    "jst": "Asia/Tokyo",
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "aest": "Australia/Brisbane",
    "aedt": "Australia/Sydney",
    "cet": "Europe/Paris",
    "cest": "Europe/Paris",
    "nzst": "Pacific/Auckland",
    "nzdt": "Pacific/Auckland",
}

WEEKDAY_ALIASES = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}

MONTH_ALIASES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def current_utc() -> datetime:
    override = (os.getenv("UT_NOW") or "").strip()
    if not override:
        return ensure_aware(datetime.now(UTC)).replace(microsecond=0)

    if re.fullmatch(r"\d{10}", override):
        return ensure_aware(datetime.fromtimestamp(int(override), UTC)).replace(
            microsecond=0
        )

    if re.fullmatch(r"\d{13}", override):
        return ensure_aware(datetime.fromtimestamp(int(override) / 1000, UTC)).replace(
            microsecond=0
        )

    iso_value = override[:-1] + "+00:00" if override.endswith("Z") else override
    dt = datetime.fromisoformat(iso_value)
    if dt.tzinfo is None:
        raise ValueError("UT_NOW must include a timezone or be an epoch")
    return ensure_aware(dt.astimezone(UTC)).replace(microsecond=0)


def resolve_zone(zone: str) -> str:
    normalized = zone.strip()
    return ZONE_ALIASES.get(normalized.lower(), normalized)


def get_zoneinfo(zone: str) -> ZoneInfo:
    return ZoneInfo(zone)


def is_valid_timezone(zone: str) -> bool:
    try:
        get_zoneinfo(zone)
        return True
    except ZoneInfoNotFoundError:
        return False


def unique_zones(zones: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for zone in zones:
        if not zone or not is_valid_timezone(zone):
            continue
        if zone in seen:
            continue
        seen.add(zone)
        result.append(zone)

    return result


def tz_abbreviation(dt: datetime, zone: str) -> str:
    aware = ensure_aware(dt)
    return aware.astimezone(get_zoneinfo(zone)).tzname() or zone


def format_time_for_display(zoned: datetime) -> str:
    if USE_12H:
        hour_text = zoned.strftime("%I:%M:%S %p").lstrip("0")
        if hour_text.startswith(":"):
            hour_text = "0" + hour_text
        return hour_text
    return zoned.strftime("%H:%M:%S")


def format_time_compact(zoned: datetime) -> str:
    if USE_12H:
        hour_text = zoned.strftime("%I:%M %p").lstrip("0")
        if hour_text.startswith(":"):
            hour_text = "0" + hour_text
        return hour_text
    return zoned.strftime("%H:%M")


def format_in_zone(dt: datetime, zone: str) -> str:
    aware = ensure_aware(dt)
    zoned = aware.astimezone(get_zoneinfo(zone))
    return (
        f"{zoned.strftime(DATE_FORMAT)} "
        f"{format_time_for_display(zoned)} "
        f"{tz_abbreviation(aware, zone)}"
    )


def format_compact_in_zone(dt: datetime, zone: str) -> str:
    aware = ensure_aware(dt)
    zoned = aware.astimezone(get_zoneinfo(zone))
    return (
        f"{zoned.strftime(COMPACT_DATE_FORMAT)} "
        f"{format_time_compact(zoned)} "
        f"{tz_abbreviation(aware, zone)}"
    )


def format_markdown_in_zone(dt: datetime, zone: str) -> str:
    aware = ensure_aware(dt)
    zoned = aware.astimezone(get_zoneinfo(zone))
    base = zoned.strftime(MARKDOWN_DATE_FORMAT)
    if "%H" in MARKDOWN_DATE_FORMAT or "%I" in MARKDOWN_DATE_FORMAT:
        return f"{base} {tz_abbreviation(aware, zone)}"
    return f"{base} {format_time_compact(zoned)} {tz_abbreviation(aware, zone)}"


def format_rfc3339(dt: datetime) -> str:
    aware = ensure_aware(dt)
    return (
        aware.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def format_discord_timestamp(dt: datetime) -> str:
    aware = ensure_aware(dt)
    return f"<t:{int(aware.timestamp())}:{DISCORD_STYLE}>"


def iso_utc(dt: datetime) -> str:
    aware = ensure_aware(dt)
    return (
        aware.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def is_valid_date_parts(year: int, month: int, day: int) -> bool:
    if month < 1 or month > 12 or day < 1:
        return False

    try:
        datetime(year, month, day, tzinfo=UTC)
        return True
    except ValueError:
        return False


def is_valid_time_parts(hour: int, minute: int, second: int) -> bool:
    return 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59


def get_today_parts_in_zone(zone: str) -> tuple[int, int, int]:
    now = current_utc().astimezone(get_zoneinfo(zone))
    return now.year, now.month, now.day


def get_current_year_in_zone(zone: str) -> int:
    return current_utc().astimezone(get_zoneinfo(zone)).year


def parse_clock_time(text: str) -> tuple[int, int, int] | None:
    s = text.strip().lower()

    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*(am|pm)?", s)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    second = int(match.group(3) or 0)
    meridiem = match.group(4)

    if meridiem:
        if hour < 1 or hour > 12:
            return None
        if meridiem == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12

    if not is_valid_time_parts(hour, minute, second):
        return None

    return hour, minute, second


def parse_date_time_like(text: str) -> dict[str, int | bool] | None:
    s = text.strip()

    match = re.fullmatch(
        r"(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*(am|pm)?",
        s,
        re.IGNORECASE,
    )
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        time_part = parse_clock_time(
            f"{match.group(4)}"
            f"{':' + match.group(5) if match.group(5) else ''}"
            f"{':' + match.group(6) if match.group(6) else ''}"
            f"{match.group(7) or ''}"
        )
        if time_part is None:
            return None

        hour, minute, second = time_part

        if not is_valid_date_parts(year, month, day):
            return None

        return {
            "has_date": True,
            "year": year,
            "month": month,
            "day": day,
            "hour": hour,
            "minute": minute,
            "second": second,
        }

    time_part = parse_clock_time(s)
    if time_part is not None:
        hour, minute, second = time_part
        return {
            "has_date": False,
            "hour": hour,
            "minute": minute,
            "second": second,
        }

    return None


def parse_calendar_date(
    text: str, zone: str
) -> tuple[int, int, int] | ParseErrorResult | None:
    s = text.strip()

    iso_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if iso_match:
        year = int(iso_match.group(1))
        month = int(iso_match.group(2))
        day = int(iso_match.group(3))
        if not is_valid_date_parts(year, month, day):
            return ParseErrorResult("Could not parse input.")
        return year, month, day

    month_name_match = re.fullmatch(
        r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,\s*|\s+)?(\d{4})?",
        s,
        re.IGNORECASE,
    )
    if not month_name_match:
        return None

    month_token = month_name_match.group(1).lower()
    month = MONTH_ALIASES.get(month_token)
    if month is None:
        return None

    day = int(month_name_match.group(2))
    year = int(month_name_match.group(3) or get_current_year_in_zone(zone))

    if not is_valid_date_parts(year, month, day):
        return ParseErrorResult("Could not parse input.")

    return year, month, day


def parse_duration_with_units(text: str) -> timedelta | None:
    parts = list(
        re.finditer(
            r"(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)",
            text.strip().lower(),
        )
    )
    if not parts:
        return None

    normalized = re.sub(
        r"(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)",
        "",
        text.strip().lower(),
    )
    if normalized.strip():
        return None

    delta = timedelta(0)
    for part in parts:
        value = int(part.group(1))
        unit = part.group(2)
        if unit.startswith(("second", "sec")) or unit == "s":
            delta += timedelta(seconds=value)
        elif unit.startswith(("minute", "min")) or unit == "m":
            delta += timedelta(minutes=value)
        elif unit.startswith(("hour", "hr")) or unit == "h":
            delta += timedelta(hours=value)
        elif unit.startswith("day") or unit == "d":
            delta += timedelta(days=value)
        else:
            delta += timedelta(weeks=value)

    return delta


def parse_date_arithmetic_offset(text: str) -> timedelta | None:
    s = text.strip().lower()

    if re.fullmatch(r"\d+", s):
        return timedelta(days=int(s))

    clock_match = re.fullmatch(r"(\d{1,3}):(\d{2})(?::(\d{2}))?", s)
    if clock_match:
        hours = int(clock_match.group(1))
        minutes = int(clock_match.group(2))
        seconds = int(clock_match.group(3) or 0)
        if minutes > 59 or seconds > 59:
            return None
        return timedelta(hours=hours, minutes=minutes, seconds=seconds)

    return parse_duration_with_units(s)


def parse_date_arithmetic_parts(
    date_text: str, operator: str, offset_text: str, zone: str
) -> dict[str, int | bool] | ParseErrorResult | None:
    parsed_date = parse_calendar_date(date_text, zone)
    if parsed_date is None:
        return None
    if isinstance(parsed_date, ParseErrorResult):
        return parsed_date

    offset = parse_date_arithmetic_offset(offset_text)
    if offset is None:
        return ParseErrorResult("Could not parse input.")

    year, month, day = parsed_date
    sign = 1 if operator == "+" else -1
    target_local = datetime(year, month, day) + (sign * offset)

    return {
        "has_date": True,
        "year": target_local.year,
        "month": target_local.month,
        "day": target_local.day,
        "hour": target_local.hour,
        "minute": target_local.minute,
        "second": target_local.second,
    }


def parse_date_arithmetic(
    text: str, zone: str
) -> dict[str, int | bool] | ParseErrorResult | None:
    s = text.strip()

    iso_match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\s*([+-])\s*(.+)", s)
    if iso_match:
        return parse_date_arithmetic_parts(
            iso_match.group(1), iso_match.group(2), iso_match.group(3), zone
        )

    month_name_match = re.fullmatch(
        r"([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*|\s+)?(?:\d{4})?)\s*([+-])\s*(.+)",
        s,
        re.IGNORECASE,
    )
    if month_name_match:
        return parse_date_arithmetic_parts(
            month_name_match.group(1),
            month_name_match.group(2),
            month_name_match.group(3),
            zone,
        )

    return None


def parse_relative_weekday(text: str, zone: str) -> dict[str, int | bool] | None:
    s = text.strip().lower()
    match = re.fullmatch(
        r"(next\s+)?"
        r"(mon|monday|tue|tues|tuesday|wed|wednesday|thu|thur|thurs|thursday|fri|friday|sat|saturday|sun|sunday)"
        r"(?:\s+(.+))?",
        s,
    )
    if not match:
        return None

    is_next = bool(match.group(1))
    weekday_name = match.group(2)
    time_text = (match.group(3) or "9am").strip()

    time_part = parse_clock_time(time_text)
    if time_part is None:
        return None

    hour, minute, second = time_part
    target_weekday = WEEKDAY_ALIASES[weekday_name]

    now_local = current_utc().astimezone(get_zoneinfo(zone))
    today_local = now_local.date()
    current_weekday = today_local.weekday()

    delta_days = (target_weekday - current_weekday) % 7
    if is_next:
        delta_days = 7 if delta_days == 0 else delta_days

    target_local = today_local + timedelta(days=delta_days)

    return {
        "has_date": True,
        "year": target_local.year,
        "month": target_local.month,
        "day": target_local.day,
        "hour": hour,
        "minute": minute,
        "second": second,
    }


def parse_relative_day(text: str, zone: str) -> dict[str, int | bool] | None:
    s = text.strip().lower()
    match = re.fullmatch(r"(today|tomorrow|yesterday|next week)\s+(.+)", s)
    if not match:
        return None

    day_token = match.group(1)
    time_text = match.group(2).strip()
    time_part = parse_clock_time(time_text)
    if time_part is None:
        return None

    hour, minute, second = time_part
    today_local = current_utc().astimezone(get_zoneinfo(zone)).date()

    if day_token == "today":
        target_date = today_local
    elif day_token == "tomorrow":
        target_date = today_local + timedelta(days=1)
    elif day_token == "yesterday":
        target_date = today_local - timedelta(days=1)
    else:
        target_date = today_local + timedelta(days=7)

    return {
        "has_date": True,
        "year": target_date.year,
        "month": target_date.month,
        "day": target_date.day,
        "hour": hour,
        "minute": minute,
        "second": second,
    }


def parse_relative_month_or_year(text: str, zone: str) -> dict[str, int | bool] | None:
    s = text.strip().lower()
    match = re.fullmatch(r"(next month|next year)\s+(.+)", s)
    if not match:
        return None

    token = match.group(1)
    time_text = match.group(2).strip()
    time_part = parse_clock_time(time_text)
    if time_part is None:
        return None

    hour, minute, second = time_part
    now_local = current_utc().astimezone(get_zoneinfo(zone))
    year = now_local.year
    month = now_local.month
    day = now_local.day

    if token == "next month":
        if month == 12:
            target_year = year + 1
            target_month = 1
        else:
            target_year = year
            target_month = month + 1
        target_day = day
    else:
        target_year = year + 1
        target_month = month
        target_day = day

    if not is_valid_date_parts(target_year, target_month, target_day):
        return {
            "error": True,
            "message": f"{token.title()} is invalid because that calendar date does not exist.",
        }

    return {
        "has_date": True,
        "year": target_year,
        "month": target_month,
        "day": target_day,
        "hour": hour,
        "minute": minute,
        "second": second,
    }


def parse_in_relative(text: str) -> timedelta | None:
    s = text.strip().lower()
    match = re.fullmatch(r"in\s+(.+)", s)
    if not match:
        return None

    rest = match.group(1)
    parts = list(
        re.finditer(
            r"(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)",
            rest,
        )
    )
    if not parts:
        return None

    normalized = re.sub(
        r"(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)",
        "",
        rest,
    )
    if normalized.strip():
        return None

    delta = timedelta(0)

    for part in parts:
        value = int(part.group(1))
        unit = part.group(2)

        if unit.startswith(("second", "sec")) or unit == "s":
            delta += timedelta(seconds=value)
        elif unit.startswith(("minute", "min")) or unit == "m":
            delta += timedelta(minutes=value)
        elif unit.startswith(("hour", "hr")) or unit == "h":
            delta += timedelta(hours=value)
        elif unit.startswith("day") or unit == "d":
            delta += timedelta(days=value)
        else:
            delta += timedelta(weeks=value)

    return delta


def looks_like_zone(token: str) -> bool:
    if not token:
        return False

    resolved = resolve_zone(token)
    return is_valid_timezone(resolved) or token.lower() in ZONE_ALIASES


def extract_forced_zone(text: str) -> dict[str, str] | None:
    s = text.strip()

    prefixed = re.fullmatch(r"([A-Za-z_./+\-]+)\s+(.+)", s)
    if prefixed and looks_like_zone(prefixed.group(1)):
        return {
            "zone": resolve_zone(prefixed.group(1)),
            "rest": prefixed.group(2).strip(),
        }

    suffixed = re.fullmatch(r"(.+)\s+([A-Za-z_./+\-]+)", s)
    if suffixed and looks_like_zone(suffixed.group(2)):
        return {
            "zone": resolve_zone(suffixed.group(2)),
            "rest": suffixed.group(1).strip(),
        }

    return None


def parse_now_offset(text: str) -> timedelta | None:
    s = text.strip().lower()
    match = re.fullmatch(r"now\s*((?:[+-]\s*\d+\s*[smhdw]\s*)*)", s)
    if not match:
        return None

    suffix = match.group(1).strip()
    if not suffix:
        return timedelta(0)

    delta = timedelta(0)
    consumed = 0

    for part in re.finditer(r"([+-])\s*(\d+)\s*([smhdw])\s*", suffix):
        consumed += len(part.group(0))
        sign = 1 if part.group(1) == "+" else -1
        value = int(part.group(2))
        unit = part.group(3)

        if unit == "s":
            chunk = timedelta(seconds=value)
        elif unit == "m":
            chunk = timedelta(minutes=value)
        elif unit == "h":
            chunk = timedelta(hours=value)
        elif unit == "d":
            chunk = timedelta(days=value)
        else:
            chunk = timedelta(weeks=value)

        delta += sign * chunk

    if consumed != len(suffix):
        return None

    return delta

def same_local_identity(left: datetime, right: datetime) -> bool:
    left_aware = ensure_aware(left)
    right_aware = ensure_aware(right)

    return (
        left_aware.year == right_aware.year
        and left_aware.month == right_aware.month
        and left_aware.day == right_aware.day
        and left_aware.hour == right_aware.hour
        and left_aware.minute == right_aware.minute
        and left_aware.second == right_aware.second
        and left_aware.utcoffset() == right_aware.utcoffset()
        and left_aware.fold == right_aware.fold
    )


def datetime_exists(local_dt: datetime) -> bool:
    aware = ensure_aware(local_dt)
    zone = aware.tzinfo
    if zone is None:
        raise ValueError("Expected timezone-aware datetime")

    round_tripped = aware.astimezone(UTC).astimezone(zone)
    return same_local_identity(aware, round_tripped)


def build_local_candidates_in_zone(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int,
    zone_name: str,
) -> list[InstantCandidate] | None:
    zone = get_zoneinfo(zone_name)

    dt_fold_0 = datetime(year, month, day, hour, minute, second, tzinfo=zone, fold=0)
    dt_fold_1 = datetime(year, month, day, hour, minute, second, tzinfo=zone, fold=1)

    exists_0 = datetime_exists(dt_fold_0)
    exists_1 = datetime_exists(dt_fold_1)

    if not exists_0 and not exists_1:
        return None

    candidates_by_iso: dict[str, InstantCandidate] = {}

    if exists_0:
        utc_0 = ensure_utc(dt_fold_0)
        candidates_by_iso[iso_utc(utc_0)] = InstantCandidate(
            instant_utc=utc_0,
            label="",
        )

    if exists_1:
        utc_1 = ensure_utc(dt_fold_1)
        candidates_by_iso[iso_utc(utc_1)] = InstantCandidate(
            instant_utc=utc_1,
            label="",
        )

    ordered = [candidates_by_iso[key] for key in sorted(candidates_by_iso.keys())]

    if len(ordered) == 2:
        return [
            InstantCandidate(
                instant_utc=ordered[0].instant_utc, label="Earlier occurrence"
            ),
            InstantCandidate(
                instant_utc=ordered[1].instant_utc, label="Later occurrence"
            ),
        ]

    return ordered


def build_parse_context(text: str) -> ParseContext:
    trimmed = text.strip()
    forced = extract_forced_zone(trimmed)
    forced_zone = forced["zone"] if forced else None
    body = forced["rest"] if forced else trimmed
    source_zone = forced_zone if forced_zone else CONFIGURED_LOCAL_TZ

    return ParseContext(
        raw_text=text,
        trimmed=trimmed,
        forced_zone=forced_zone,
        body=body,
        source_zone=source_zone,
    )


def parse_structured_local_datetime(
    parsed: dict[str, int | bool], ctx: ParseContext
) -> ParseResult:
    if bool(parsed.get("error")):
        return ParseErrorResult(str(parsed["message"]))

    if bool(parsed["has_date"]):
        year = int(parsed["year"])
        month = int(parsed["month"])
        day = int(parsed["day"])
    else:
        year, month, day = get_today_parts_in_zone(ctx.source_zone)

    candidates = build_local_candidates_in_zone(
        year,
        month,
        day,
        int(parsed["hour"]),
        int(parsed["minute"]),
        int(parsed["second"]),
        ctx.source_zone,
    )

    if candidates is None:
        return ParseErrorResult(
            f"Nonexistent local time in {ctx.source_zone} due to DST transition."
        )

    interpretation = (
        f"Interpreted in {ctx.source_zone}"
        if ctx.forced_zone
        else f"Interpreted in local timezone ({CONFIGURED_LOCAL_TZ})"
    )

    return ParsedInstant(
        candidates=candidates,
        interpretation=interpretation,
        parser_name="local-datetime",
    )


def parse_discord_timestamp(text: str) -> ParsedInstant | None:
    s = text.strip()
    match = re.fullmatch(r"<t:(\d{1,16})(?::([tTdDfFR]))?>", s)
    if not match:
        return None

    epoch_seconds = int(match.group(1))
    dt = ensure_aware(datetime.fromtimestamp(epoch_seconds, UTC)).replace(microsecond=0)
    style = match.group(2)
    interpretation = "Discord timestamp"
    if style:
        interpretation = f"Discord timestamp ({style})"

    return ParsedInstant(
        candidates=[InstantCandidate(instant_utc=dt)],
        interpretation=interpretation,
        parser_name="discord",
    )


def parser_discord_timestamp(ctx: ParseContext) -> ParseAttempt:
    parsed = parse_discord_timestamp(ctx.trimmed)
    if parsed is None:
        return ParseAttempt(handled=False)
    return ParseAttempt(handled=True, result=parsed)


def parser_explicit_instant(ctx: ParseContext) -> ParseAttempt:
    s = ctx.trimmed

    if re.fullmatch(r"\d{10}", s):
        dt = ensure_aware(datetime.fromtimestamp(int(s), UTC)).replace(microsecond=0)
        return ParseAttempt(
            handled=True,
            result=ParsedInstant(
                candidates=[InstantCandidate(instant_utc=dt)],
                interpretation="Unix seconds",
                parser_name="epoch-seconds",
            ),
        )

    if re.fullmatch(r"\d{13}", s):
        dt = ensure_aware(datetime.fromtimestamp(int(s) / 1000, UTC)).replace(
            microsecond=0
        )
        return ParseAttempt(
            handled=True,
            result=ParsedInstant(
                candidates=[InstantCandidate(instant_utc=dt)],
                interpretation="Unix milliseconds",
                parser_name="epoch-milliseconds",
            ),
        )

    iso_candidate = s[:-1] + "+00:00" if s.endswith("Z") else s
    if "T" in s or re.search(r"[+-]\d{2}:\d{2}$", s) or s.endswith("Z"):
        try:
            dt = datetime.fromisoformat(iso_candidate)
        except ValueError:
            return ParseAttempt(handled=False)

        if dt.tzinfo is None:
            return ParseAttempt(handled=False)

        return ParseAttempt(
            handled=True,
            result=ParsedInstant(
                candidates=[InstantCandidate(instant_utc=ensure_utc(dt))],
                interpretation="ISO instant",
                parser_name="iso-instant",
            ),
        )

    return ParseAttempt(handled=False)


def parser_now_relative(ctx: ParseContext) -> ParseAttempt:
    delta = parse_now_offset(ctx.body)
    if delta is None:
        return ParseAttempt(handled=False)

    dt = ensure_utc(current_utc() + delta)
    interpretation = f"Current time ({ctx.body.lower()})"
    return ParseAttempt(
        handled=True,
        result=ParsedInstant(
            candidates=[InstantCandidate(instant_utc=dt)],
            interpretation=interpretation,
            parser_name="now-relative",
        ),
    )


def parser_in_relative(ctx: ParseContext) -> ParseAttempt:
    delta = parse_in_relative(ctx.body)
    if delta is None:
        return ParseAttempt(handled=False)

    dt = ensure_utc(current_utc() + delta)
    interpretation = f"Relative time ({ctx.body.lower()})"
    return ParseAttempt(
        handled=True,
        result=ParsedInstant(
            candidates=[InstantCandidate(instant_utc=dt)],
            interpretation=interpretation,
            parser_name="in-relative",
        ),
    )


def parser_relative_month_or_year(ctx: ParseContext) -> ParseAttempt:
    parsed = parse_relative_month_or_year(ctx.body, ctx.source_zone)
    if parsed is None:
        return ParseAttempt(handled=False)

    result = parse_structured_local_datetime(parsed, ctx)
    if isinstance(result, ParsedInstant):
        return ParseAttempt(
            handled=True,
            result=ParsedInstant(
                candidates=result.candidates,
                interpretation=result.interpretation,
                parser_name="relative-month-year",
            ),
        )
    return ParseAttempt(handled=True, result=result)


def parser_relative_day(ctx: ParseContext) -> ParseAttempt:
    parsed = parse_relative_day(ctx.body, ctx.source_zone)
    if parsed is None:
        return ParseAttempt(handled=False)

    result = parse_structured_local_datetime(parsed, ctx)
    if isinstance(result, ParsedInstant):
        return ParseAttempt(
            handled=True,
            result=ParsedInstant(
                candidates=result.candidates,
                interpretation=result.interpretation,
                parser_name="relative-day",
            ),
        )
    return ParseAttempt(handled=True, result=result)


def parser_relative_weekday(ctx: ParseContext) -> ParseAttempt:
    parsed = parse_relative_weekday(ctx.body, ctx.source_zone)
    if parsed is None:
        return ParseAttempt(handled=False)

    result = parse_structured_local_datetime(parsed, ctx)
    if isinstance(result, ParsedInstant):
        return ParseAttempt(
            handled=True,
            result=ParsedInstant(
                candidates=result.candidates,
                interpretation=result.interpretation,
                parser_name="relative-weekday",
            ),
        )
    return ParseAttempt(handled=True, result=result)


def parser_date_arithmetic(ctx: ParseContext) -> ParseAttempt:
    parsed = parse_date_arithmetic(ctx.body, ctx.source_zone)
    if parsed is None:
        return ParseAttempt(handled=False)
    if isinstance(parsed, ParseErrorResult):
        return ParseAttempt(handled=True, result=parsed)

    result = parse_structured_local_datetime(parsed, ctx)
    if isinstance(result, ParsedInstant):
        return ParseAttempt(
            handled=True,
            result=ParsedInstant(
                candidates=result.candidates,
                interpretation=f"Date arithmetic in {ctx.source_zone}",
                parser_name="date-arithmetic",
            ),
        )
    return ParseAttempt(handled=True, result=result)


def parser_date_or_time(ctx: ParseContext) -> ParseAttempt:
    parsed = parse_date_time_like(ctx.body)
    if parsed is None:
        return ParseAttempt(handled=False)

    result = parse_structured_local_datetime(parsed, ctx)
    if isinstance(result, ParsedInstant):
        return ParseAttempt(
            handled=True,
            result=ParsedInstant(
                candidates=result.candidates,
                interpretation=result.interpretation,
                parser_name="date-or-time",
            ),
        )
    return ParseAttempt(handled=True, result=result)


# Parsing priority is a behavior contract. Do not reorder casually.
PARSER_CHAIN: tuple[ParserFn, ...] = (
    parser_discord_timestamp,
    parser_explicit_instant,
    parser_now_relative,
    parser_in_relative,
    parser_relative_month_or_year,
    parser_relative_day,
    parser_relative_weekday,
    parser_date_arithmetic,
    parser_date_or_time,
)


def parse_input(text: str) -> ParseResult:
    if not text:
        return HelpResult()

    ctx = build_parse_context(text)

    if ctx.forced_zone and not is_valid_timezone(ctx.source_zone):
        return ParseErrorResult(f"Invalid timezone: {ctx.source_zone}")

    if not is_valid_timezone(ctx.source_zone):
        return ParseErrorResult(f"Invalid timezone: {ctx.source_zone}")

    for parser in PARSER_CHAIN:
        attempt = parser(ctx)
        if attempt.handled:
            return attempt.result or ParseErrorResult("Could not parse input.")

    return ParseErrorResult("Could not parse input.")


def zone_item(
    parsed: ParsedInstant,
    candidate: InstantCandidate,
    zone: str,
) -> dict[str, object]:
    dt = candidate.instant_utc
    zone_value = format_in_zone(dt, zone)
    utc_value = format_in_zone(dt, "UTC")
    local_value = format_in_zone(dt, CONFIGURED_LOCAL_TZ)
    iso_value = iso_utc(dt)
    epoch_seconds = str(int(dt.timestamp()))
    markdown_value = format_markdown_in_zone(dt, zone)
    compact_value = format_compact_in_zone(dt, zone)
    rfc3339_value = format_rfc3339(dt)
    discord_value = format_discord_timestamp(dt)

    title_prefix = f"{candidate.label} · " if candidate.label else ""
    subtitle = f"{parsed.interpretation} → Enter copies formatted time"
    if DEBUG_MODE:
        subtitle = f"{subtitle} · parser={parsed.parser_name}"

    return {
        "title": f"{title_prefix}{zone}: {zone_value}",
        "subtitle": subtitle,
        "arg": zone_value,
        "mods": {
            "cmd": {"arg": iso_value, "subtitle": "Copy ISO"},
            "alt": {"arg": epoch_seconds, "subtitle": "Copy Unix seconds"},
            "ctrl": {"arg": utc_value, "subtitle": "Copy UTC formatted"},
            "shift": {
                "arg": local_value,
                "subtitle": "Copy configured local formatted",
            },
            "fn": {
                "arg": markdown_value,
                "subtitle": "Copy markdown-friendly format",
            },
            "cmd+alt": {
                "arg": discord_value,
                "subtitle": "Copy Discord timestamp",
            },
            "cmd+ctrl": {
                "arg": rfc3339_value,
                "subtitle": "Copy RFC 3339",
            },
            "alt+shift": {
                "arg": compact_value,
                "subtitle": "Copy compact format",
            },
        },
    }


def utility_items(candidate: InstantCandidate) -> list[dict[str, object]]:
    dt = candidate.instant_utc
    iso_value = iso_utc(dt)
    epoch_seconds = int(dt.timestamp())
    epoch_millis = int(dt.timestamp() * 1000)
    rfc3339_value = format_rfc3339(dt)
    discord_value = format_discord_timestamp(dt)
    compact_value = format_compact_in_zone(dt, CONFIGURED_LOCAL_TZ)
    markdown_value = format_markdown_in_zone(dt, CONFIGURED_LOCAL_TZ)
    prefix = f"{candidate.label} · " if candidate.label else ""

    return [
        {
            "title": f"{prefix}Discord timestamp: {discord_value}",
            "subtitle": "Copy Discord timestamp",
            "arg": discord_value,
        },
        {
            "title": f"{prefix}Compact: {compact_value}",
            "subtitle": "Copy compact format",
            "arg": compact_value,
        },
        {
            "title": f"{prefix}Markdown: {markdown_value}",
            "subtitle": "Copy markdown-friendly format",
            "arg": markdown_value,
        },
        {
            "title": f"{prefix}ISO: {iso_value}",
            "subtitle": "Copy ISO 8601 instant",
            "arg": iso_value,
        },
        {
            "title": f"{prefix}Unix seconds: {epoch_seconds}",
            "subtitle": "Copy Unix epoch seconds",
            "arg": str(epoch_seconds),
        },
        {
            "title": f"{prefix}Unix milliseconds: {epoch_millis}",
            "subtitle": "Copy Unix epoch milliseconds",
            "arg": str(epoch_millis),
        },
        {
            "title": f"{prefix}RFC 3339: {rfc3339_value}",
            "subtitle": "Copy RFC 3339",
            "arg": rfc3339_value,
        },
    ]


def render_items(result: ParseResult) -> list[dict[str, object]]:
    if isinstance(result, HelpResult):
        return [
            {
                "title": "Enter a time to convert",
                "subtitle": (
                    "Examples: now · now+1h · in 3 hours · tomorrow 9am · "
                    "next monday · next month 9am · April 1 +7 · 9am PST · <t:1711540800:f>"
                ),
                "valid": False,
            }
        ]

    if isinstance(result, ParseErrorResult):
        return [
            {
                "title": "Invalid input",
                "subtitle": result.message,
                "valid": False,
            }
        ]

    display_zones = unique_zones(
        [
            CONFIGURED_LOCAL_TZ,
            "UTC",
            *OUTPUT_ZONES_RAW,
        ]
    )

    items: list[dict[str, object]] = []

    for candidate in result.candidates:
        for zone in display_zones:
            items.append(zone_item(result, candidate, zone))
        items.extend(utility_items(candidate))

    return items


def main() -> int:
    raw = " ".join(sys.argv[1:]).strip()
    result = parse_input(raw)
    items = render_items(result)
    sys.stdout.write(json.dumps({"items": items}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, ZoneInfoNotFoundError, json.JSONDecodeError) as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "items": [
                        {
                            "title": "Workflow error",
                            "subtitle": str(exc),
                            "valid": False,
                        }
                    ]
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(0)
