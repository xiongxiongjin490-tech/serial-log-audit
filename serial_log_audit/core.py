"""Time-series log validation and channel statistics, implemented independently.

The module works on plain CSV captures exported from an embedded controller or
serial monitor. It does not bundle any firmware, driver, device protocol, or
hardware model. Structural problems (duplicate frames, non-finite numbers,
out-of-order timestamps) are rejected loudly; range violations and sampling
gaps are collected as auditable anomalies instead of being silently dropped.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_COLUMNS = {"timestamp", "channel", "value"}
OPTIONAL_COLUMNS = {"status"}


@dataclass(frozen=True)
class Sample:
    """One captured reading on one channel."""

    timestamp: float
    channel: str
    value: float
    status: str | None = None

    @property
    def key(self) -> tuple[str, float]:
        return self.channel, self.timestamp


@dataclass(frozen=True)
class ChannelSpec:
    """Expected operating bounds and nominal sampling period for one channel."""

    min_value: float | None = None
    max_value: float | None = None
    period_s: float | None = None


@dataclass(frozen=True)
class Anomaly:
    timestamp: float
    channel: str
    kind: str
    detail: str
    value: float | None = None

    def as_row(self) -> dict[str, str]:
        return {
            "timestamp": f"{self.timestamp:.6f}",
            "channel": self.channel,
            "kind": self.kind,
            "detail": self.detail,
            "value": "" if self.value is None else f"{self.value:.6f}",
        }


def load_limits(path: str | Path) -> dict[str, ChannelSpec]:
    """Load an optional JSON limits file.

    Schema: {"channels": {"<name>": {"min": -10.0, "max": 85.0, "period_s": 1.0}}}.
    Missing bounds mean "no range check for this channel"; missing period means
    "do not detect sampling gaps".
    """
    source = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = source.get("channels", {})
    specs: dict[str, ChannelSpec] = {}
    for name, entry in raw.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Channel names must be nonempty strings")
        min_value = entry.get("min")
        max_value = entry.get("max")
        period_s = entry.get("period_s")
        if min_value is not None and not math.isfinite(float(min_value)):
            raise ValueError(f"min for {name} must be finite")
        if max_value is not None and not math.isfinite(float(max_value)):
            raise ValueError(f"max for {name} must be finite")
        if min_value is not None and max_value is not None and min_value > max_value:
            raise ValueError(f"min exceeds max for {name}")
        if period_s is not None and (not math.isfinite(float(period_s)) or float(period_s) <= 0):
            raise ValueError(f"period_s for {name} must be a positive number")
        specs[name] = ChannelSpec(
            min_value=None if min_value is None else float(min_value),
            max_value=None if max_value is None else float(max_value),
            period_s=None if period_s is None else float(period_s),
        )
    return specs


def load_samples(path: str | Path) -> list[Sample]:
    """Parse and structurally validate a CSV capture."""
    samples: list[Sample] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}")
        extra = set(reader.fieldnames or []) - REQUIRED_COLUMNS - OPTIONAL_COLUMNS
        if extra:
            raise ValueError(f"Unexpected CSV columns: {', '.join(sorted(extra))}")
        for line, row in enumerate(reader, 2):
            try:
                if None in row:
                    raise ValueError("Extra CSV fields")
                raw_ts = (row["timestamp"] or "").strip()
                raw_channel = (row["channel"] or "").strip()
                raw_value = (row["value"] or "").strip()
                raw_status = (row.get("status") or "").strip()
                if not raw_channel:
                    raise ValueError("channel must be nonempty")
                timestamp = float(raw_ts)
                value = float(raw_value)
                if not math.isfinite(timestamp):
                    raise ValueError("timestamp must be finite")
                if not math.isfinite(value):
                    raise ValueError("value must be finite")
                samples.append(Sample(timestamp, raw_channel, value, raw_status or None))
            except (ValueError, TypeError) as error:
                raise ValueError(f"CSV line {line}: {error}") from error
    validate_structure(samples)
    return samples


def validate_structure(samples: list[Sample]) -> None:
    """Reject duplicate frames and non-monotonic per-channel timestamps."""
    if not samples:
        raise ValueError("No samples found")
    seen: set[tuple[str, float]] = set()
    last: dict[str, float] = {}
    for sample in samples:
        if not math.isfinite(sample.timestamp):
            raise ValueError("timestamp must be finite")
        if not math.isfinite(sample.value):
            raise ValueError("value must be finite")
        if sample.key in seen:
            raise ValueError(f"Duplicate frame: {sample.channel} @ {sample.timestamp}")
        seen.add(sample.key)
        previous = last.get(sample.channel)
        if previous is not None and sample.timestamp <= previous:
            raise ValueError(
                f"Out-of-order timestamp on {sample.channel}: {sample.timestamp} <= {previous}"
            )
        last[sample.channel] = sample.timestamp


def _channel_summary(channel: str, rows: list[Sample], spec: ChannelSpec | None) -> dict:
    values = [row.value for row in rows]
    period = spec.period_s if spec else None
    gaps: list[dict[str, float]] = []
    bursts: list[dict[str, float]] = []
    out_of_range: list[Sample] = []

    for row in rows:
        if spec is not None:
            if spec.min_value is not None and row.value < spec.min_value:
                out_of_range.append(row)
            elif spec.max_value is not None and row.value > spec.max_value:
                out_of_range.append(row)

    if period is not None:
        for earlier, later in zip(rows, rows[1:]):
            interval = later.timestamp - earlier.timestamp
            if interval > 1.5 * period:
                gaps.append({"after": earlier.timestamp, "before": later.timestamp, "interval": interval})
            elif interval < 0.5 * period:
                bursts.append({"after": earlier.timestamp, "before": later.timestamp, "interval": interval})

    return {
        "channel": channel,
        "samples": len(rows),
        "first_timestamp": rows[0].timestamp,
        "last_timestamp": rows[-1].timestamp,
        "duration_s": rows[-1].timestamp - rows[0].timestamp,
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else None,
        "out_of_range": len(out_of_range),
        "sampling_gaps": len(gaps),
        "dense_bursts": len(bursts),
        "_gaps": gaps,
        "_bursts": bursts,
        "_out_of_range": out_of_range,
    }


def audit(samples: list[Sample], limits: dict[str, ChannelSpec] | None = None) -> dict:
    """Group samples by channel, compute statistics and collect anomalies."""
    validate_structure(samples)
    limits = limits or {}
    groups: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        groups[sample.channel].append(sample)

    channels: list[dict] = []
    anomalies: list[Anomaly] = []
    for channel, rows in sorted(groups.items()):
        spec = limits.get(channel)
        summary = _channel_summary(channel, rows, spec)

        for row in summary.pop("_out_of_range"):
            bound = "below_min" if spec and spec.min_value is not None and row.value < spec.min_value else "above_max"
            anomalies.append(Anomaly(row.timestamp, channel, "out_of_range", bound, row.value))
        for gap in summary.pop("_gaps"):
            anomalies.append(Anomaly(gap["before"], channel, "sampling_gap",
                                     f"interval {gap['interval']:.3f}s after {gap['after']:.3f}s"))
        for burst in summary.pop("_bursts"):
            anomalies.append(Anomaly(burst["before"], channel, "dense_burst",
                                    f"interval {burst['interval']:.3f}s after {burst['after']:.3f}s"))
        channels.append(summary)

    anomalies.sort(key=lambda item: (item.channel, item.timestamp, item.kind))
    return {
        "total_samples": len(samples),
        "channel_count": len(channels),
        "channels": channels,
        "anomalies": [
            {"timestamp": a.timestamp, "channel": a.channel, "kind": a.kind,
             "detail": a.detail, "value": a.value}
            for a in anomalies
        ],
    }


def input_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
