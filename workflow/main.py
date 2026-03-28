#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass
class Candidate:
    date: datetime
    source_label: str
    label: str = ""

    def __post_init__(self) -> None:
        if self.date.tzinfo is None:
            raise ValueError("Candidate.date must be timezone-aware")


@dataclass
class ParsedResult:
    candidates: list[Candidate] = field(default_factory=list)
    error: str | None = None
    help: bool = False


def ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("Expected timezone-aware datetime")
    return dt


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

OUTPUT_ZONES_RAW = [
    (os.getenv("UT_TZ1") or "").strip(),
    (os.getenv("UT_TZ2") or "").strip(),
    (os.getenv("UT_TZ3") or "").strip(),
    (os.getenv("UT_TZ4") or "").strip(),
]
OUTPUT_ZONES_RAW = [zone for zone in OUTPUT_ZONES_RAW if zone]

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


def format_in_zone(dt: datetime, zone: str) -> str:
    aware = ensure_aware(dt)
    zoned = aware.astimezone(get_zoneinfo(zone))
    return f"{zoned.strftime('%Y-%m-%d %H:%M:%S')} {tz_abbreviation(aware, zone)}"


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


def parse_epoch_or_instant(text: str) -> ParsedResult | None:
    s = text.strip()

    if re.fullmatch(r"\d{10}", s):
        dt = ensure_aware(datetime.fromtimestamp(int(s), UTC))
        return ParsedResult(
            candidates=[Candidate(date=dt, source_label="Unix seconds")]
        )

    if re.fullmatch(r"\d{13}", s):
        dt = ensure_aware(datetime.fromtimestamp(int(s) / 1000, UTC))
        return ParsedResult(
            candidates=[Candidate(date=dt, source_label="Unix milliseconds")]
        )

    iso_candidate = s[:-1] + "+00:00" if s.endswith("Z") else s
    if "T" in s or re.search(r"[+-]\d{2}:\d{2}$", s) or s.endswith("Z"):
        try:
            dt = datetime.fromisoformat(iso_candidate)
        except ValueError:
            return None

        if dt.tzinfo is None:
            return None

        return ParsedResult(
            candidates=[
                Candidate(
                    date=ensure_aware(dt.astimezone(UTC)), source_label="ISO instant"
                )
            ]
        )

    return None


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


def parse_relative_weekday(text: str, zone: str) -> dict[str, int | bool] | None:
    s = text.strip().lower()
    match = re.fullmatch(
        r"(next\s+)?(mon|monday|tue|tues|tuesday|wed|wednesday|thu|thur|thurs|thursday|fri|friday|sat|saturday|sun|sunday)\s+(.+)",
        s,
    )
    if not match:
        return None

    is_next = bool(match.group(1))
    weekday_name = match.group(2)
    time_text = match.group(3).strip()

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
    elif delta_days == 0:
        delta_days = 0

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
            "position": "prefix",
        }

    suffixed = re.fullmatch(r"(.+)\s+([A-Za-z_./+\-]+)", s)
    if suffixed and looks_like_zone(suffixed.group(2)):
        return {
            "zone": resolve_zone(suffixed.group(2)),
            "rest": suffixed.group(1).strip(),
            "position": "suffix",
        }

    return None


def parse_now_offset(text: str) -> timedelta | None:
    match = re.fullmatch(r"now((?:[+-]\d+[smhdw])*)", text.strip().lower())
    if not match:
        return None

    suffix = match.group(1)
    if not suffix:
        return timedelta(0)

    delta = timedelta(0)
    consumed = 0

    for part in re.finditer(r"([+-])(\d+)([smhdw])", suffix):
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


def build_datetime_candidates_in_zone(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int,
    zone_name: str,
    source_label: str,
) -> ParsedResult:
    zone = get_zoneinfo(zone_name)

    dt_fold_0 = datetime(
        year,
        month,
        day,
        hour,
        minute,
        second,
        tzinfo=zone,
        fold=0,
    )
    dt_fold_1 = datetime(
        year,
        month,
        day,
        hour,
        minute,
        second,
        tzinfo=zone,
        fold=1,
    )

    exists_0 = datetime_exists(dt_fold_0)
    exists_1 = datetime_exists(dt_fold_1)

    if not exists_0 and not exists_1:
        return ParsedResult(
            error=f"Nonexistent local time in {zone_name} due to DST transition."
        )

    candidates_by_iso: dict[str, datetime] = {}

    if exists_0:
        utc_dt_0 = ensure_aware(dt_fold_0.astimezone(UTC))
        candidates_by_iso[iso_utc(utc_dt_0)] = utc_dt_0

    if exists_1:
        utc_dt_1 = ensure_aware(dt_fold_1.astimezone(UTC))
        candidates_by_iso[iso_utc(utc_dt_1)] = utc_dt_1

    candidates = [candidates_by_iso[key] for key in sorted(candidates_by_iso.keys())]

    if len(candidates) == 1:
        return ParsedResult(
            candidates=[Candidate(date=candidates[0], source_label=source_label)]
        )

    return ParsedResult(
        candidates=[
            Candidate(
                date=candidates[0],
                source_label=source_label,
                label="Earlier occurrence",
            ),
            Candidate(
                date=candidates[1],
                source_label=source_label,
                label="Later occurrence",
            ),
        ]
    )


def parse_input(text: str) -> ParsedResult:
    if not text:
        return ParsedResult(help=True)

    trimmed = text.strip()

    forced = extract_forced_zone(trimmed)
    body = forced["rest"] if forced else trimmed
    source_zone = forced["zone"] if forced else CONFIGURED_LOCAL_TZ

    if forced and not is_valid_timezone(source_zone):
        return ParsedResult(error=f"Invalid timezone: {source_zone}")

    delta = parse_now_offset(body)
    if delta is not None:
        dt = ensure_aware(current_utc() + delta)
        label = body.lower()
        source_label = f"Current time ({label})"
        if forced:
            source_label = f"{source_label} with explicit timezone token {source_zone}"
        return ParsedResult(candidates=[Candidate(date=dt, source_label=source_label)])

    instant = parse_epoch_or_instant(trimmed)
    if instant is not None:
        return instant

    if not is_valid_timezone(source_zone):
        return ParsedResult(error=f"Invalid timezone: {source_zone}")

    parsed = parse_relative_weekday(body, source_zone)
    if parsed is None:
        parsed = parse_date_time_like(body)

    if parsed is None:
        return ParsedResult(error="Could not parse input.")

    if bool(parsed["has_date"]):
        year = int(parsed["year"])
        month = int(parsed["month"])
        day = int(parsed["day"])
    else:
        year, month, day = get_today_parts_in_zone(CONFIGURED_LOCAL_TZ)

    source_label = (
        f"Interpreted in {source_zone}"
        if forced
        else f"Interpreted in local timezone ({CONFIGURED_LOCAL_TZ})"
    )

    return build_datetime_candidates_in_zone(
        year,
        month,
        day,
        int(parsed["hour"]),
        int(parsed["minute"]),
        int(parsed["second"]),
        source_zone,
        source_label,
    )


def zone_item(candidate: Candidate, zone: str) -> dict[str, object]:
    dt = ensure_aware(candidate.date.astimezone(UTC))
    zone_value = format_in_zone(dt, zone)
    title_prefix = f"{candidate.label} · " if candidate.label else ""
    subtitle_prefix = f"{candidate.label} · " if candidate.label else ""
    iso_value = iso_utc(dt)
    epoch_seconds = str(int(dt.timestamp()))

    return {
        "title": f"{title_prefix}{zone}: {zone_value}",
        "subtitle": f"{subtitle_prefix}{candidate.source_label} → Enter copies formatted time",
        "arg": zone_value,
        "mods": {
            "cmd": {
                "arg": iso_value,
                "subtitle": f"{subtitle_prefix}Copy ISO",
            },
            "alt": {
                "arg": epoch_seconds,
                "subtitle": f"{subtitle_prefix}Copy Unix seconds",
            },
        },
    }


def utility_items(candidate: Candidate) -> list[dict[str, object]]:
    dt = ensure_aware(candidate.date.astimezone(UTC))
    iso_value = iso_utc(dt)
    epoch_seconds = int(dt.timestamp())
    epoch_ms = int(dt.timestamp() * 1000)
    prefix = f"{candidate.label} · " if candidate.label else ""

    return [
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
            "title": f"{prefix}Unix milliseconds: {epoch_ms}",
            "subtitle": "Copy Unix epoch milliseconds",
            "arg": str(epoch_ms),
        },
    ]


def build_items(parsed: ParsedResult) -> list[dict[str, object]]:
    if parsed.help:
        return [
            {
                "title": "Enter a time to convert",
                "subtitle": "Examples: now · now+1h · now-30m · 1711540800 · 12:30 utc · next monday 9am · 9am PST",
                "valid": False,
            }
        ]

    if parsed.error:
        return [
            {
                "title": "Invalid input",
                "subtitle": parsed.error,
                "valid": False,
            }
        ]

    display_zones = unique_zones(
        [
            CONFIGURED_LOCAL_TZ,
            *OUTPUT_ZONES_RAW,
            "UTC",
        ]
    )

    items: list[dict[str, object]] = []

    for candidate in parsed.candidates:
        for zone in display_zones:
            items.append(zone_item(candidate, zone))
        items.extend(utility_items(candidate))

    return items


def main() -> int:
    raw = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    items = build_items(parse_input(raw))
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
