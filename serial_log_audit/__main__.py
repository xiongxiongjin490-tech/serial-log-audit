"""Command-line interface: ``python -m serial_log_audit ...``."""

from __future__ import annotations

import argparse
import csv
import json
import platform
import sys
from pathlib import Path

from . import __version__
from .core import ChannelSpec, Sample, audit, input_sha256, load_limits, load_samples
from .synthetic import demo_limits, demo_samples


def _write_channel_csv(path: Path, channels: list[dict]) -> None:
    fields = ["channel", "samples", "first_timestamp", "last_timestamp", "duration_s",
              "mean", "median", "min", "max", "stdev", "out_of_range",
              "sampling_gaps", "dense_bursts"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in channels:
            writer.writerow({key: row.get(key) for key in fields})


def _write_anomaly_csv(path: Path, anomalies: list[dict]) -> None:
    fields = ["timestamp", "channel", "kind", "detail", "value"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in anomalies:
            writer.writerow({key: ("" if row.get(key) is None else row.get(key)) for key in fields})


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.4f}"


def _render_markdown(report: dict, data_kind: str) -> str:
    lines = [
        "# 时序日志质检报告",
        "",
        f"- 数据类型：`{data_kind}`（来源标签由使用者声明，工具不做真实性认证）",
        f"- 总样本数：{report['total_samples']}",
        f"- 通道数：{report['channel_count']}",
        f"- 异常条目：{len(report['anomalies'])}",
        "",
        "## 逐通道统计",
        "",
        "| 通道 | 样本 | 均值 | 中位数 | 最小 | 最大 | 标准差 | 越界 | 丢帧 | 密集突发 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["channels"]:
        lines.append(
            f"| {row['channel']} | {row['samples']} | {_fmt(row['mean'])} | {_fmt(row['median'])} | "
            f"{_fmt(row['min'])} | {_fmt(row['max'])} | {_fmt(row['stdev'])} | "
            f"{row['out_of_range']} | {row['sampling_gaps']} | {row['dense_bursts']} |"
        )
    lines += ["", "## 异常清单", ""]
    if report["anomalies"]:
        lines += ["| 时间戳 | 通道 | 类型 | 说明 | 数值 |", "| ---: | --- | --- | --- | ---: |"]
        for item in report["anomalies"]:
            lines.append(
                f"| {item['timestamp']:.6f} | {item['channel']} | {item['kind']} | "
                f"{item['detail']} | {_fmt(item['value'])} |"
            )
    else:
        lines.append("未发现越界、丢帧或密集突发异常。")
    lines.append("")
    return "\n".join(lines)


def _persist(output_dir: Path, report: dict, data_kind: str,
             source: str | None, limits: dict[str, ChannelSpec]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "tool": "serial-log-audit",
        "version": __version__,
        "data_kind": data_kind,
        "source": source,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "limits": {
            name: {"min": spec.min_value, "max": spec.max_value, "period_s": spec.period_s}
            for name, spec in limits.items()
        },
        "report": report,
    }
    (output_dir / "report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_channel_csv(output_dir / "channel_summary.csv", report["channels"])
    _write_anomaly_csv(output_dir / "anomalies.csv", report["anomalies"])
    (output_dir / "report.md").write_text(_render_markdown(report, data_kind), encoding="utf-8")


def _export_samples_csv(path: Path, samples: list[Sample]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "channel", "value", "status"])
        writer.writeheader()
        for row in samples:
            writer.writerow({"timestamp": f"{row.timestamp:.6f}", "channel": row.channel,
                             "value": f"{row.value:.6f}", "status": row.status or ""})


def _cmd_demo(args: argparse.Namespace) -> int:
    samples = demo_samples()
    limits = demo_limits()
    report = audit(samples, limits)
    output = Path(args.output)
    _persist(output, report, "synthetic-demo", "fixed-seed artificial capture", limits)
    if not args.quick:
        _export_samples_csv(output / "synthetic_log.csv", samples)
    if args.docs:
        docs = Path(args.docs)
        docs.parent.mkdir(parents=True, exist_ok=True)
        docs.write_text(json.dumps({"data_kind": "synthetic-demo", "report": report},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    samples = load_samples(args.input)
    limits = load_limits(args.config) if args.config else {}
    report = audit(samples, limits)
    digest = input_sha256(args.input)
    _persist(Path(args.output), report, args.data_kind, digest, limits)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="serial-log-audit", description="时序日志校验与统计")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="生成固定种子的合成演示日志并质检")
    demo.add_argument("--output", default="results")
    demo.add_argument("--docs", help="额外写出供页面读取的 data.json")
    demo.add_argument("--quick", action="store_true", help="只写报告，不导出原始合成 CSV")
    demo.set_defaults(handler=_cmd_demo)

    audit_cmd = sub.add_parser("audit", help="审计一份真实/外部 CSV 日志")
    audit_cmd.add_argument("input", help="输入 CSV，必需列 timestamp,channel,value")
    audit_cmd.add_argument("--output", default="report")
    audit_cmd.add_argument("--config", help="可选 JSON 限值与采样周期配置")
    audit_cmd.add_argument("--data-kind", default="external-unverified",
                           help="数据来源标签，默认 external-unverified")
    audit_cmd.set_defaults(handler=_cmd_audit)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
