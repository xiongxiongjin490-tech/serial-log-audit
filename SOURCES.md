# Sources and provenance

1. Python standard library documentation: [csv](https://docs.python.org/3/library/csv.html),
   [statistics](https://docs.python.org/3/library/statistics.html), [math](https://docs.python.org/3/library/math.html),
   [hashlib](https://docs.python.org/3/library/hashlib.html) and [json](https://docs.python.org/3/library/json.html).
   Parsing, descriptive statistics, finite-number checks and SHA-256 hashing are implemented on the
   standard library; no third-party runtime package is required.
2. Sample standard deviation uses the `n - 1` denominator, matching
   [statistics.stdev](https://docs.python.org/3/library/statistics.html#statistics.stdev).
3. The gap / burst thresholds (1.5× and 0.5× the nominal period) are local heuristics defined in
   `serial_log_audit/core.py`; they are not a published sampling-rate standard.

The demo generator in `serial_log_audit/synthetic.py` uses `random.Random(2026)` to create two
artificial channels under label `synthetic-demo`. Channel names `temperature` and `current` are
illustrative. The generated readings do not come from any real controller, sensor, firmware build,
or hardware bench session.

Files in `results/` can be rebuilt with `python -m serial_log_audit demo`. The input SHA-256 for
external captures is recorded in `report.json`. No original researcher affiliation, authorship,
or award is attributed to this account.
