# Serial Log Audit · 嵌入式时序日志质检台

[English](README.en.md) · [来源说明](SOURCES.md) · [AI 辅助说明](AI_USE.md)

把控制器 / 串口导出的时序 CSV 变成可审查的质检报告：先拒绝重复帧、乱序时间戳和非有限数值，再按通道做描述统计、越界识别与采样间隔异常检测。项目独立编写，不包含任何固件、驱动、通信协议或硬件模型。

**当前演示使用程序生成的合成日志，不是本人的硬件实测采集，不代表任何真实控制器的运行数据。** 原始 99 条合成记录、逐通道统计与异常清单都在 [results/](results/)。

## 能力与成果

- 校验缺失列、未知列、非数值 / NaN / Inf 读数、重复 `(channel, timestamp)` 帧和同通道乱序时间戳。
- 按通道计算样本数、首末时间戳、时长、均值、中位数、最小 / 最大值与样本标准差。
- 依据可选限值配置识别越界读数；依据标称采样周期检测丢帧间隔（>1.5×周期）与密集突发（<0.5×周期）。
- 导出 JSON 报告、逐通道汇总 CSV、异常清单 CSV 和 Markdown 报告，记录输入 SHA-256 与运行环境。

## 快速复跑

Python 3.10+。运行时只依赖标准库；运行测试需要 pytest。

```bash
python -m pip install -e ".[dev]"
python -m serial_log_audit demo
python -m pytest
```

默认重建 `results/` 与网页读取的 `docs/data.json`。CI 可用独立目录：

```bash
python -m serial_log_audit demo --quick --output results-quick --docs results-quick/data.json
```

## 分析自己的日志

```bash
python -m serial_log_audit audit my_capture.csv --output my-report --config limits.json
```

CSV 必需列为 `timestamp,channel,value`；可选列 `status`。`timestamp` 与 `value` 必须是有限数值，同一通道内时间戳必须严格递增。

```csv
timestamp,channel,value,status
0.000,temperature,25.31,ok
1.000,temperature,25.40,ok
0.000,current,1.18,ok
```

限值与采样周期通过可选 JSON 配置传入；未配置的通道只做结构校验，不做越界 / 间隔判定：

```json
{
  "channels": {
    "temperature": {"min": -10.0, "max": 85.0, "period_s": 1.0},
    "current": {"min": 0.0, "max": 5.0, "period_s": 0.5}
  }
}
```

`period_s` 应由使用者绑定到实际采样设置；代码无法核验现实采样率是否一致。外部输入默认为 `external-unverified`，来源标签是用户声明，不是认证。CLI 在输入无效时返回退出码 2。

## 如何解读结果

`results/report.md` 是报告入口，`channel_summary.csv` 保留每个通道的分母与统计量，`anomalies.csv` 保留逐条异常。标准差为样本标准差（`n - 1`）；单通道样本不足 2 条时标准差记为空。越界与间隔异常属于数据质量提示，不等同于传感器故障或控制回路失效；不同硬件、不同口径的读数不能直接横向比较。

## 项目边界

本项目受嵌入式日志质检与数据质量审查的通用需求启发，实际实现是独立的 CSV 校验与统计工具；**没有复现任何固件采集流程，也不绑定具体硬件型号**。只引用标准库文档，未复制上游代码、数据集或设备厂商资料。见 [SOURCES.md](SOURCES.md)。代码采用 MIT 许可；引用资料保留其原有权利。

## 固定环境与验证

使用 Python 3.12。锁文件包含开发、构建及跨平台运行依赖，首次安装后即可复跑：

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-build-isolation --no-deps -e .
python -m pytest -q
python -m serial_log_audit demo
```

更新演示数据后，重新执行 `python -m serial_log_audit demo` 即可重建报告。统计结果会因机器与随机种子固定而可复现；真实采集的数值口径由使用者负责。
