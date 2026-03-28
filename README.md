# Alfred Time Converter

Inspired by [UnixTime Converter](https://github.com/ytakahashi/alfred-unixtime-converter) by [ytakahashi](https://github.com/ytakahashi)

A fast, zero-dependency **Alfred workflow** to convert between:

- ISO timestamps
- Unix epoch (seconds & milliseconds)
- Local time ↔ UTC ↔ multiple timezones

With powerful parsing like:

```
ut now
ut now+1h
ut 12:30 utc
ut utc 12:30
ut 9am PST
ut next monday 9am
ut 2026-03-27T12:00:00Z
ut 1711540800
```

# ✨ Features

### 🕒 Flexible input parsing

- ISO 8601 timestamps
- Unix epoch (seconds & ms)
- Local time (`12:30`, `9am`)
- Timezone-aware input (`12:30 utc`, `pst 9am`)
- Relative time:
  - `now`
  - `now+1h`
  - `now-30m`
  - `now+1h-15m`

---

### 🌍 Timezone support

- Configurable local timezone
- Up to 4 additional output timezones
- Common aliases:
  - `pst`, `est`, `gmt`, `utc`, `jst`, etc.

---

### 🧠 Natural language

```
ut next monday 9am
ut friday 14:30
ut pst next monday 9am
```

---

### 🧪 Correct DST handling

- ❌ Rejects nonexistent times (spring forward)
- ⚠️ Returns both results for ambiguous times (fall back)

Example:

```
2026-11-01 01:30 America/Vancouver
→ Earlier occurrence
→ Later occurrence
```

---

### ⚡ Alfred integration

- **Enter** → copy formatted time
- **⌘ Enter** → copy ISO timestamp
- **⌥ Enter** → copy Unix epoch

---

# 📦 Installation

### Option 1 — Download release

1. Go to GitHub Releases
2. Download:

```
UT-Time-Converter.alfredworkflow
```

1. Open it → Alfred installs automatically

---

### Option 2 — Build locally

```bash
make build-workflow
open UT-Time-Converter.alfredworkflow
```

---

# ⚙️ Configuration

You can configure timezones via Alfred workflow variables:

| Variable      | Description            | Example             |
| ------------- | ---------------------- | ------------------- |
| `UT_LOCAL_TZ` | Default local timezone | `America/Vancouver` |
| `UT_TZ1`      | Extra output timezone  | `UTC`               |
| `UT_TZ2`      | Extra output timezone  | `America/New_York`  |
| `UT_TZ3`      | Extra output timezone  | `Europe/London`     |
| `UT_TZ4`      | Extra output timezone  | `Asia/Tokyo`        |

---

# 🧪 Development

### Run locally

```bash
python3 workflow/main.py "now"
```

---

### Run tests

```bash
make test
```

Tests cover:

- ISO / epoch parsing
- timezone conversions
- DST edge cases
- natural language parsing
- modifier outputs

---

### Build artifacts

```bash
make build              # source zip
make build-workflow     # Alfred workflow file
```

- **Timezone-safe** (no naive datetimes)
- **Deterministic parsing**
- **Minimal runtime cost**
- **Works offline**

---

# 🪪 License

Apache License 2.0
