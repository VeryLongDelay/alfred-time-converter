# Alfred Time Converter

Inspired by [UnixTime Converter](https://github.com/ytakahashi/alfred-unixtime-converter) by [ytakahashi](https://github.com/ytakahashi)

A fast, dependency-free Alfred workflow for converting between:A fast, dependency-free Alfred workflow for converting between:

- Unix epoch timestamps
- local times
- UTC
- configurable timezones

It is built for quick keyboard-driven use inside Alfred and supports both strict timezone handling and flexible natural-language input.

## Features

### Supported input styles

Examples:

```text
ut now
ut now+1h
ut now-30m
ut now+1h-15m
ut in 3 hours
ut in 90 minutes
ut 1711540800
ut 1711540800000
ut 2026-03-27T12:00:00Z
ut 2026-03-27T12:00:00+09:00
ut 12:30
ut 9am
ut utc 12:30
ut 12:30 utc
ut PST 9am
ut 9am PST
ut tokyo 09:00
ut 09:00 tokyo
ut today 9am
ut tomorrow 9am
ut yesterday 9am
ut next week 9am
ut monday 9am
ut next monday 9am
ut next monday 9am JST
```

### Timezone support

- configurable local timezone
- up to 4 additional output timezones
- common aliases and abbreviations:
  - `utc`, `z`, `gmt`
  - `pst`, `pdt`
  - `mst`, `mdt`
  - `cst`, `cdt`
  - `est`, `edt`
  - `jst`

### Strict DST handling

- rejects nonexistent local times during spring-forward transitions
- returns both valid occurrences during fall-back ambiguity

For example, an ambiguous time like:

```text
ut 2026-11-01 01:30 America/Vancouver
```

returns:

- Earlier occurrence
- Later occurrence

### Copy modifiers in Alfred

On any timezone result row:

- `Enter` → copy formatted time
- `⌘ Enter` → copy ISO
- `⌥ Enter` → copy Unix seconds
- `⌃ Enter` → copy UTC formatted
- `⇧ Enter` → copy configured local formatted
- `fn Enter` → copy markdown-friendly format
- `⌘⌥ Enter` → copy Discord timestamp
- `⌘⌃ Enter` → copy RFC 3339
- `⌥⇧ Enter` → copy compact format

### Output formats

The workflow provides:

- formatted timezone display
- ISO 8601
- Unix seconds
- Unix milliseconds
- RFC 3339
- Discord timestamps
- compact format
- markdown-friendly format

## Installation

### Install from a release

Download the latest:

```text
UT-Time-Converter.alfredworkflow
```

Then open it to install into Alfred.

### Build locally

```bash
make build-workflow
open UT-Time-Converter.alfredworkflow
```

## Configuration

Configure these Alfred workflow variables:

| Variable                  | Description                         | Example             |
| ------------------------- | ----------------------------------- | ------------------- |
| `UT_LOCAL_TZ`             | default local timezone              | `America/Vancouver` |
| `UT_TZ1`                  | extra output timezone               | `UTC`               |
| `UT_TZ2`                  | extra output timezone               | `America/New_York`  |
| `UT_TZ3`                  | extra output timezone               | `Europe/London`     |
| `UT_TZ4`                  | extra output timezone               | `Asia/Tokyo`        |
| `UT_USE_12H`              | 12-hour display toggle (`0` or `1`) | `0`                 |
| `UT_DATE_FORMAT`          | main output date format             | `%Y-%m-%d`          |
| `UT_COMPACT_DATE_FORMAT`  | compact output date format          | `%Y-%m-%d`          |
| `UT_MARKDOWN_DATE_FORMAT` | markdown-friendly date format       | `%Y-%m-%d %H:%M`    |
| `UT_DISCORD_STYLE`        | Discord timestamp style             | `f`                 |

Suggested defaults:

```text
UT_LOCAL_TZ=America/Vancouver
UT_TZ1=UTC
UT_TZ2=America/New_York
UT_TZ3=Europe/London
UT_TZ4=Asia/Tokyo
UT_USE_12H=0
UT_DATE_FORMAT=%Y-%m-%d
UT_COMPACT_DATE_FORMAT=%Y-%m-%d
UT_MARKDOWN_DATE_FORMAT=%Y-%m-%d %H:%M
UT_DISCORD_STYLE=f
```

## Example outputs

### Standard formatted output

```text
America/Vancouver: 2026-03-27 05:00:00 PDT
UTC: 2026-03-27 12:00:00 UTC
Asia/Tokyo: 2026-03-27 21:00:00 JST
```

### Discord timestamp

```text
<t:1774612800:f>
```

### RFC 3339

```text
2026-03-27T12:00:00Z
```

### Compact

```text
2026-03-27 05:00 PDT
```

## Natural language parsing rules

Supported without external libraries:

- `now`
- `now+1h`
- `now-30m`
- chained offsets like `now+1h-15m+30s`
- `in 3 hours`
- `in 90 minutes`
- `today 9am`
- `tomorrow 9am`
- `yesterday 9am`
- `next week 9am`
- `monday 9am`
- `next monday 9am`

## Abbreviation parsing behavior

Abbreviations are interpreted deterministically using fixed mappings:

- `PST` / `PDT` → `America/Vancouver`
- `MST` / `MDT` → `America/Denver`
- `CST` / `CDT` → `America/Chicago`
- `EST` / `EDT` → `America/New_York`
- `JST` → `Asia/Tokyo`
- `UTC` / `GMT` / `Z` → `UTC`

This avoids region-dependent ambiguity.

## Development

### Run locally

```bash
python3 workflow/main.py "now"
python3 workflow/main.py "next monday 9am"
python3 workflow/main.py "9am PST"
```

### Run tests

```bash
make test
```

The test suite covers:

- ISO parsing
- epoch parsing
- timezone forcing
- configured timezone deduplication
- DST gap and overlap behavior
- natural language parsing
- modifier output targets

### Build artifacts

```bash
make build
make build-workflow
```

## License

Apache License 2.0

```Apache License 2.0

```
