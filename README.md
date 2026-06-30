# 港股新股打新每日分析系统

一个可审计、可离线运行的港股 IPO 研究流水线。首版优先打通：

1. HKEXnews 主板/GEM 新上市资料列表；
2. 招股书 PDF 下载与保守字段提取；
3. `manual_override.csv` 手工补充融资热度和关键日历；
4. SQLite + 原始 JSON + CSV 汇总 + Markdown 日报；
5. 基于明确阈值的确定性评分和数据缺失扣分。

> 本项目只用于个人研究和数据整理，不构成任何投资建议。不要将自动提取结果直接用于交易；应回看字段对应的 `source_url` 并核验招股书原文。

## 当前边界

- 不绕过登录、验证码、付费墙或券商风控。
- 券商孖展数据首版不自动抓取，只读取手工 CSV。
- PDF 表格版式差异很大。首版仅对高置信度文本模式做保守提取；无法确认的字段保持 `null`。
- HKEX 页面变化时，抓取器会记录异常，仍可用本地 JSON + 手工 CSV 跑通报告。
- 同行选择、估值判断、保荐人质量、基石质量等不能靠名称猜测；首版接受已核验字段，不自动编造。

## 项目结构

```text
config/config.yaml                   # 数据源、限速、路径、评分配置
data/manual_override.csv             # 手工融资热度和关键日期
data/raw/YYYY-MM-DD/*.json           # 带逐字段来源的原始记录
data/prospectuses/                   # 下载的招股书
data/daily_ipo_summary.csv           # 每日扁平汇总
reports/YYYY-MM-DD_hk_ipo_report.md  # 日报
src/hk_ipo_analyzer/
  ipo_fetcher/                       # HKEX、PDF、手工热度、日历
  ipo_parser/                        # 招股书、财务、基石、风险
  analysis/                          # 板块、同行、评分、建议
  pipeline.py                        # 每日流水线
  storage.py                         # SQLite 与 JSON
tests/                               # 离线单元测试
examples/sample_ipo.json             # 离线闭环示例
```

## 安装

需要 Python 3.11 或更高版本。

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

如后续数据源确实需要动态渲染，再安装可选依赖（首版 HKEX 流程不需要）：

```bash
python -m pip install -e '.[browser]'
playwright install chromium
```

## 配置

编辑 `config/config.yaml`：

- 把 `http.user_agent` 中的联系邮箱改成真实邮箱；
- `min_interval_seconds` 默认同域名请求至少间隔 2 秒；
- `respect_robots_txt: true` 不建议关闭；
- 可调整数据库、报告和数据目录；
- `scoring.hot_sectors` 只是规则输入，应根据可验证的市场状态维护。

官方入口：

- HKEXnews 主板新上市资料：<https://www2.hkexnews.hk/New-Listings/New-Listing-Information/Main-Board?sc_lang=zh-HK>
- HKEXnews GEM 新上市资料：<https://www2.hkexnews.hk/New-Listings/New-Listing-Information/GEM?sc_lang=zh-HK>
- HKEX 新上市证券：<https://www.hkex.com.hk/Services/Trading/Securities/Trading-News/Newly-Listed-Securities?sc_lang=zh-HK>

使用前请自行复核上述网站最新条款、robots.txt 和允许用途。本项目默认只读取公开页面，遇到禁止抓取会停止该请求。

## 运行

### 1. 先跑离线闭环

不联网、不下载 PDF：

```bash
hk-ipo daily --date 2026-06-30 --input-json examples/sample_ipo.json --skip-pdf
```

输出：

- `reports/2026-06-30_hk_ipo_report.md`
- `data/daily_ipo_summary.csv`
- `data/raw/2026-06-30/9999.json`
- `data/hk_ipo.db`

### 2. 获取 HKEX 当前记录

```bash
hk-ipo daily
```

若只想验证列表与手工数据，不下载招股书：

```bash
hk-ipo daily --skip-pdf
```

### 3. 前台定时运行

每天上海时间 08:00：

```bash
hk-ipo schedule --hour 8 --minute 0
```

生产环境也可使用 cron：

```cron
0 8 * * * cd /绝对路径/港股打新 && /绝对路径/.venv/bin/hk-ipo daily >> logs/cron.log 2>&1
```

## 手工补充融资倍率和日期

编辑 `data/manual_override.csv`，一行代表某只股票在某个日期的数据快照。股票代码应保留前导零，例如 `01234`。

```csv
stock_code,company_name,as_of_date,margin_amount_hkd,margin_multiple,expected_oversubscription,actual_oversubscription,grey_market_return_pct,news_heat_score,offer_start_date,offer_end_date,pricing_date,allotment_result_date,listing_date,source_url,source_name,fetched_at,notes
01234,示例公司,2026-06-30,5000000000,25,30,,,2,2026-06-30,2026-07-03,2026-07-04,2026-07-09,2026-07-10,https://example.com/source,人工核验的公开来源,2026-06-30T08:00:00+08:00,已核对页面
```

规则：

- 同一股票多行时，热度模块选取不晚于报告日的最新 `as_of_date`；
- 空单元格写入 `null`，不会用零代替；
- `news_heat_score` 范围为 0–3；
- `source_url/source_name/fetched_at` 应尽量填写，否则报告仍会把该字段标为来源信息不完整；
- 暗盘数据只有暗盘开始后才填写；不要把预测值写到实际字段。

如需一次性补充更完整的财务、发行结构或同行字段，可复制 `examples/sample_ipo.json`，给每个字段填写 `value/source_url/source_name/fetched_at`，再用 `--input-json` 运行。

## 数据追溯

每个字段在 Python 中都表示为：

```json
{
  "value": 35.0,
  "source_url": "https://...",
  "source_name": "HKEX 招股书",
  "fetched_at": "2026-06-30T00:00:00+00:00"
}
```

这些证据保存在：

- 当日原始 JSON；
- SQLite 的 `field_evidence` 表；
- `ipo_daily.record_json` 完整快照。

CSV 是便于筛选的扁平摘要，不替代证据库。

## 评分方法

各维度严格使用用户设定上限：基本面 25、行业 15、发行结构 15、基石 15、市场热度 20，合计为 90。由于目标总分要求为 100，系统采用：

```text
总分 = clamp((五维原始得分 / 90) × 100 - 风险扣分, 0, 100)
```

风险扣分最多 20 分。缺失字段不获分，核心字段缺失还会额外扣 0–8 分；报告同步输出 `confidence`。规则阈值均在 `analysis/scoring_model.py`，没有调用生成式模型给分。

推荐区间：

| 总分 | 结论 |
| ---: | --- |
| 85–100 | 积极打新 |
| 75–84.9 | 现金一手 |
| 65–74.9 | 谨慎一手 |
| 55–64.9 | 不建议打新，可观察 |
| <55 | 放弃 |

当可信度偏低时，即便分数达到区间，策略文字也会明确提示数据不足。

## 测试

```bash
pytest -q
ruff check src tests
```

测试完全离线，不访问 HKEX。

## 常见问题

**日报为空怎么办？** 先查看 `logs/hk_ipo.log`。常见原因是 HKEX 页面结构变化、网络失败或 robots 规则禁止。可用 `examples/sample_ipo.json` 验证本地流水线，再更新抓取适配器。

**为什么很多字段是“缺失”？** 这是刻意的保守行为。PDF 表格提取不可靠时，系统宁愿输出 `null`，也不会根据上下文猜数。

**能否自动抓券商孖展？** 后续可以为明确允许公开访问且条款许可的页面添加适配器；不会绕过登录、验证码、付费墙或反爬限制。

## 免责声明

本项目及其报告仅用于个人研究和数据整理，不构成任何投资建议。港股 IPO 存在破发、流动性不足、融资成本、中签率不确定、市场波动等风险，投资者需自行判断并承担风险。

