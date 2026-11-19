"""Synthetic demonstration captures.

Everything produced here is artificial data generated with a fixed local seed.
It is not a firmware log, not a hardware bench capture, and it must not be
presented as a real controller measurement.
"""

from __future__ import annotations

import random

from .core import ChannelSpec, Sample

SEED = 2026


def demo_samples() -> list[Sample]:
    """Two correlated-looking artificial channels with planted anomalies."""
    rng = random.Random(SEED)
    samples: list[Sample] = []

    # temperature: 1.0 s nominal period, mild noise around 25 C.
    for step in range(60):
        if step == 30:
            continue  # planted sampling gap: one frame skipped, interval doubles
        timestamp = float(step)
        value = 25.0 + rng.gauss(0, 0.6)
        if step == 45:
            value = 91.4  # planted upper-range violation
        samples.append(Sample(timestamp, "temperature", round(value, 3)))

    # current: 0.5 s nominal period, noise around 1.2 A.
    for step in range(40):
        timestamp = step * 0.5
        value = 1.2 + rng.gauss(0, 0.08)
        if step == 20:
            value = -0.6  # planted lower-range violation
        samples.append(Sample(timestamp, "current", round(value, 3)))

    samples.sort(key=lambda row: (row.channel, row.timestamp))
    return samples


def demo_limits() -> dict[str, ChannelSpec]:
    return {
        "temperature": ChannelSpec(min_value=-10.0, max_value=85.0, period_s=1.0),
        "current": ChannelSpec(min_value=0.0, max_value=5.0, period_s=0.5),
    }
