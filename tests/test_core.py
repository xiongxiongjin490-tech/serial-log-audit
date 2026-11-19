import csv
import json

import pytest

from serial_log_audit import ChannelSpec, Sample, audit, load_limits, load_samples
from serial_log_audit.__main__ import main


def make_sample(timestamp=0.0, channel="ch", value=1.0, status=None):
    return Sample(timestamp, channel, value, status)


def test_summary_known_values():
    rows = [make_sample(float(i), "ch", float(i)) for i in range(1, 6)]  # 1..5
    report = audit(rows)
    ch = report["channels"][0]
    assert ch["samples"] == 5
    assert ch["mean"] == 3.0
    assert ch["median"] == 3.0
    assert ch["min"] == 1.0
    assert ch["max"] == 5.0
    assert ch["stdev"] == pytest.approx(1.5811388300841898)


def test_out_of_range_detected():
    spec = {"ch": ChannelSpec(min_value=0.0, max_value=10.0)}
    rows = [make_sample(0.0, "ch", 1.0), make_sample(1.0, "ch", 12.0),
            make_sample(2.0, "ch", -3.0)]
    report = audit(rows, spec)
    kinds = [item["kind"] for item in report["anomalies"]]
    assert kinds.count("out_of_range") == 2
    assert report["channels"][0]["out_of_range"] == 2


def test_sampling_gap_and_burst():
    spec = {"ch": ChannelSpec(period_s=1.0)}
    rows = [make_sample(0.0, "ch", 1.0), make_sample(2.5, "ch", 1.0),
            make_sample(2.6, "ch", 1.0), make_sample(3.6, "ch", 1.0)]
    report = audit(rows, spec)
    kinds = [item["kind"] for item in report["anomalies"]]
    assert "sampling_gap" in kinds
    assert "dense_burst" in kinds


def test_duplicate_frame_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        audit([make_sample(0.0), make_sample(0.0)])


def test_out_of_order_rejected():
    with pytest.raises(ValueError, match="Out-of-order"):
        audit([make_sample(1.0), make_sample(0.0)])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_value_rejected(value):
    with pytest.raises(ValueError, match="finite"):
        audit([make_sample(0.0, value=value)])


def test_limits_config_validation(tmp_path):
    bad = tmp_path / "limits.json"
    bad.write_text(json.dumps({"channels": {"ch": {"min": 5, "max": 1}}}))
    with pytest.raises(ValueError, match="min exceeds max"):
        load_limits(bad)


def _write_csv(tmp_path, rows, header=("timestamp", "channel", "value", "status")):
    path = tmp_path / "input.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(header))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def test_csv_load_and_missing_column(tmp_path):
    path = _write_csv(tmp_path, [{"timestamp": "0", "channel": "ch", "value": "1.0", "status": ""}])
    assert len(load_samples(path)) == 1
    broken = tmp_path / "broken.csv"
    broken.write_text("timestamp,value\n0,1.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing CSV columns"):
        load_samples(broken)


@pytest.mark.parametrize("field,value", [("timestamp", "abc"), ("value", "nan"), ("channel", "")])
def test_csv_bad_values(tmp_path, field, value):
    row = {"timestamp": "0", "channel": "ch", "value": "1.0"}
    row[field] = value
    path = _write_csv(tmp_path, [row])
    with pytest.raises(ValueError):
        load_samples(path)


def test_cli_demo_end_to_end(tmp_path):
    output = tmp_path / "results"
    docs = tmp_path / "data.json"
    assert main(["demo", "--output", str(output), "--docs", str(docs)]) == 0
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["data_kind"] == "synthetic-demo"
    assert report["report"]["total_samples"] == 99
    assert (output / "channel_summary.csv").exists()
    assert (output / "anomalies.csv").exists()
    assert (output / "report.md").exists()
    assert json.loads(docs.read_text(encoding="utf-8"))["data_kind"] == "synthetic-demo"


def test_cli_audit_invalid_returns_nonzero(tmp_path):
    missing = tmp_path / "missing.csv"
    assert main(["audit", str(missing), "--output", str(tmp_path / "out")]) == 2


def test_cli_audit_real_csv(tmp_path):
    path = _write_csv(tmp_path, [
        {"timestamp": "0", "channel": "ch", "value": "1.0", "status": "ok"},
        {"timestamp": "1", "channel": "ch", "value": "2.0", "status": "ok"},
    ])
    output = tmp_path / "report"
    assert main(["audit", str(path), "--output", str(output)]) == 0
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["data_kind"] == "external-unverified"
    assert report["report"]["channel_count"] == 1
