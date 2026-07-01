# 港股新股打新每日分析系统

本项目抓取并核验港股 IPO 发行资料、招股书财务数据、基石与市场热度，生成 Markdown/HTML 日报及可追溯证据库。报告采用确定性规则和双轨评分，仅用于研究，不构成投资建议。

## 项目边界

- 不绕过登录、验证码、付费墙或网站访问限制。
- 缺失数据保持缺失；明确“无基石/无绿鞋”分别记录为 `0` 和 `false`。
- 暗盘、配发和实际超购在公布前标记为“尚未公布”，不作为当期缺失处罚。
- 富途 OpenAPI 在 IPO 阶段主要提供列表和基础资料，不保证提供财务、基石或孖展。

## 数据流

```text
HKEX/本地核验名单
  → etnet 与可选 Futu OpenAPI 补充
  → HKEX 招股书 PDF 解析
  → 字段候选证据与来源分级
  → 官方视图 / 增强视图
  → 双轨评分
  → Markdown + HTML + CSV + SQLite
```

来源优先级、字段可用性和失败降级见 [docs/data-sources.md](docs/data-sources.md)。评分规则见 [docs/scoring.md](docs/scoring.md)。

## 安装与配置

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
export PYTHONPATH=src
```

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\pip.exe install -e ".[dev]"
$env:PYTHONPATH = "src"
```

主配置位于 `config/config.yaml`。FutuOpenD 为可选能力，默认地址是 `127.0.0.1:11111`；未安装或未启动时流水线自动跳过。

## 快速运行

使用核验 JSON 生成指定日期报告：

```bash
.venv/bin/python -m hk_ipo_analyzer daily \
  --date 2026-06-30 \
  --input-json data/verified_current_ipos_2026-06-30.json \
  --skip-pdf \
  --offline
```

Windows：

```powershell
.venv\Scripts\python.exe -m hk_ipo_analyzer daily `
  --date 2026-06-30 `
  --input-json data\verified_current_ipos_2026-06-30.json `
  --skip-pdf `
  --offline
```

在线抓取并解析招股书：

```bash
.venv/bin/python -m hk_ipo_analyzer daily
```

输出包括：

- `reports/YYYY-MM-DD_hk_ipo_report.md`
- `reports/YYYY-MM-DD_hk_ipo_report.html`
- `data/daily_ipo_summary.csv`
- `data/hk_ipo.db`
- `data/raw/YYYY-MM-DD/*.json`

## 字段证据与双轨评分

每次取数都会保存为候选证据：

```json
{
  "value": 10388000000,
  "source_url": "https://...",
  "source_name": "HKEX 招股书",
  "fetched_at": "2026-06-30T08:00:00+08:00",
  "source_tier": "A",
  "period": "FY2025",
  "currency": "RMB"
}
```

- 官方分：A 级一手来源 + 最新完整财年。
- 增强分：A/B 级来源 + 最新可比期间。
- C 级启发式或期间不明数据只展示，不评分。
- 原 CSV `score/confidence/recommendation` 保持为官方分；增强结果使用 `enhanced_*` 列。

富途网页财务数据应作为带期间的可选输入，不能直接覆盖招股书年度数据。`data/verified_current_ipos_2026-06-30_futu.json` 保留为来源快照，规范化结果使用不带来源后缀的日期 JSON。

## 报告与 skills

项目内 skills 位于 `skills/`，覆盖 IPO 分析、评分、孖展热度、中签区间、暗盘、可比公司、估值、上市日策略及报告 UI。

中签率只有在超购倍数和公开发售比例均可用时才输出区间；孖展倍数不会被当作超购倍数。

## 手工补充

实时孖展或已核验字段可写入 `data/manual_override.csv`。每条数据必须带 `as_of_date`，并尽量填写 `source_url/source_name/fetched_at`。同一股票使用报告日之前最近的快照。

## 测试与排错

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
git diff --check
```

- 日报为空：检查招股起止日期及 `logs/hk_ipo.log`。
- PDF 无数据：确认下载文件是真正 PDF，并查看字段证据；解析失败不会猜数。
- AAStocks 返回 403：这是已知限制，不影响默认流水线。
- FutuOpenD 不可用：流水线会在短时端口检测后跳过。

## 免责声明

本项目及其报告仅用于个人研究和数据整理，不构成投资建议。港股 IPO 存在破发、流动性不足、融资成本、中签率不确定及市场波动等风险，使用者需自行核验并承担风险。
