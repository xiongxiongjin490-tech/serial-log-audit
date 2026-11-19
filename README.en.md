# Serial Log Audit · Embedded time-series log audit

[中文](README.md) · [Sources](SOURCES.md) · [AI disclosure](AI_USE.md)

Turn controller / serial-exported time-series CSV into an auditable quality report:
duplicate frames, out-of-order timestamps and non-finite numbers are rejected first,
then per-channel descriptive statistics, range violations and sampling-interval anomalies
are collected. The project is implemented independently and bundles no firmware, driver,
protocol, or hardware model.

**The bundled demo uses programmatically generated synthetic logs. They are not hardware
bench captures and do not represent any real controller.** The 99 synthetic records,
per-channel summaries and anomaly list are in [results/](results/).

## Features

- Rejects missing/unknown columns, non-numeric / NaN / Inf readings, duplicate
  `(channel, timestamp)` frames and out-of-order per-channel timestamps.
- Per-channel count, first/last timestamp, duration, mean, median, min, max and sample
  standard deviation.
- Optional limits detect out-of-range readings; an optional nominal period detects sampling
  gaps (>1.5× period) and dense bursts (<0.5× period).
- Exports a JSON report, per-channel summary CSV, anomaly CSV and Markdown report, with the
  input SHA-256 and runtime environment recorded.

## Quick start

Python 3.10+. Runtime depends on the standard library only; pytest is needed for tests.

```bash
python -m pip install -e ".[dev]"
python -m serial_log_audit demo
python -m pytest
```

Rebuild `results/` and `docs/data.json` by default. For an isolated CI run:

```bash
python -m serial_log_audit demo --quick --output results-quick --docs results-quick/data.json
```

## Auditing your own capture

```bash
python -m serial_log_audit audit my_capture.csv --output my-report --config limits.json
```

Required CSV columns: `timestamp,channel,value`; optional column `status`. Timestamps and
values must be finite, and timestamps must be strictly increasing within a channel.

Limits and the nominal period are passed through an optional JSON file; channels without a
config are structurally validated only. External input defaults to `external-unverified`;
the source label is a user declaration, not an authentication. The CLI exits with code 2 on
invalid input.

## Interpreting results

`report.md` is the entry point; `channel_summary.csv` keeps per-channel denominators and
statistics, `anomalies.csv` keeps one row per anomaly. Standard deviation is the sample
standard deviation (`n - 1`) and is left empty when a channel has fewer than two readings.
Range and interval flags are data-quality signals, not evidence of sensor failure or a
control-loop fault; readings from different hardware or different measurement conventions
must not be compared directly.

## Boundaries

This is an independent CSV validation and statistics utility inspired by generic embedded
log quality review. It does not reproduce any firmware capture pipeline and is not tied to
a specific hardware model. See [SOURCES.md](SOURCES.md). Code is MIT licensed; cited
materials retain their original rights.

## Reproducible environment

Python 3.12. The lock file pins development, build and cross-platform runtime dependencies:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-build-isolation --no-deps -e .
python -m pytest -q
python -m serial_log_audit demo
```
