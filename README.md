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


## 取数逻辑与数据流 (2026-06-30 整理)

### 数据源优先级与可用性

| 数据源 | 字段 | 可用性 | 方式 |
|--------|------|--------|------|
| etnet | 基石名单/占比/金额、保荐人ID、募资规模 | ✅ 稳定 | `etnet_fetcher.py` HTTP 抓取 |
| Futu (富途) | 营收、净利润、营收增速、净利润增速 | ⚠️ 需浏览器 | 通过 Codex 内置浏览器自动化抓取 |
| AAStocks | 孖展、暗盘 | ❌ 403 | 已被反爬封锁 |
| HKEX | 历史IPO列表 | ⚠️ 间歇 | `historical.py` |
| PDF 招股书 | 毛利率、现金流、负债率、客户集中度 | ⚠️ 需下载 | `prospectus_downloader.py` |

### JSON 数据结构关键发现

输入 JSON 有两种记录格式，Pipeline 根据是否含 `verified_fields` 决定读取方式：

```text
记录 A：直接字段（无 verified_fields）
{ "stock_code": "02523", "revenue": {...}, "net_profit": {...} }
→ pipeline._load_input() 调用 IPORecord.from_dict(row)

记录 B：verified_fields 包裹（有 verified_fields）
{ "stock_code": "02523", "verified_fields": { "revenue": 149000000, ... } }
→ pipeline._load_input() 只读取 verified_fields 内的字段，忽略顶级字段！
```

**重要**：如果用 `--input-json` 加载，所有补充字段必须放在 `verified_fields` 内，否则 Pipeline 不会读取。

### 评分模型字段依赖

评分模型 (`scoring_model.py`) 的 `_fundamentals` 方法使用的是**比率类字段**，而非绝对值：

| 评分维度 | 使用字段 | 权重 | 来源 |
|----------|---------|------|------|
| 增长 | `revenue_growth_pct` | 0-6 | Futu 财务页 |
| 盈利 | `net_margin_pct` | 0-6 | **可从 revenue/net_profit 推导** |
| 毛利 | `gross_margin_latest` | 0-4 | 需 PDF 招股书 |
| 现金流 | `operating_cash_flow` | 0-4 | 需 PDF 招股书 |
| 稳健性 | `debt_to_assets_pct` | 0-3 | 需 PDF 招股书 |
| 集中度 | `customer_concentration_top5` | 0-2 | 需 PDF 招股书 |

`revenue` 和 `net_profit` 绝对值本身不被评分模型直接使用，但可以通过 `net_margin_pct = net_profit / revenue × 100` 推导出利润率来获得评分。

### Futu 富途数据抓取方法

**前置条件**：富途网站对中国大陆 IP 有限制（显示服务暂停通知），需使用 Codex 内置浏览器（通过 Playwright），浏览器网络层不受沙箱限制。

**已知可用的 Futu URL 模式**：

```text
https://www.futunn.com/stock/{CODE}-HK           # 股票概览页 ✅
https://www.futunn.com/stock/{CODE}-HK/earnings  # 财务数据页 ✅ (有营收/净利/增长率)
https://www.futunn.com/stock/{CODE}-HK/company   # 公司信息页 ✅ (董事/业务/基本资料)
https://www.futunn.com/stock/{CODE}-HK/ipo       # IPO专区 ❌ 404
https://www.futunn.com/ipo                       # IPO列表 ❌ 404
https://www.futunn.com/en/hk-ipo                 # 英文IPO ❌ 404
```

**提取模式**（从 `.../earnings` 页面）：
```python
# 财务数据在页面文本中的位置（用正则提取）：
营收 \n -- \n {数值}{亿|万} \n -- \n {+X%}
净利润 \n -- \n {数值}{亿|万} \n -- \n {+X%}
```

**限制**：仅已有交易页面的股票可获取财务数据。仍在招股期、尚未挂牌的股票（如 01770、06880、07656 等 7 只）在富途无财务页面，返回空。

### Pipeline 修复记录

**修复 `pipeline.py`** (2026-06-30)：移除了 `if not input_json:` 守卫条件。

```diff
- if not input_json:
-     self._fetch_online_sources(records)
+ self._fetch_online_sources(records)  # always enrich from etnet/aastocks
```

原因：使用 `--input-json` 加载本地数据时，原来的代码会跳过 etnet 在线补充（基石/保荐人），导致这些字段永远为空。修复后 etnet 始终运行，本地 JSON 已有的字段不会被覆盖（etnet fetcher 遵循"不覆盖已有值"的策略）。

### 字段推导规则

从已获取字段可自动推导的字段：

| 推导字段 | 公式 | 前提条件 |
|----------|------|----------|
| `net_margin_pct` | `net_profit / revenue × 100` | revenue > 0 且 net_profit 有值 |
| `entry_fee_hkd` | `offer_price_high × board_lot × 1.01` | 已有价格和手数（Pipeline 自动） |

### 当前数据覆盖状态

```
16 只新股中：
├── 基本面（revenue/net_profit）：✅ 9/16  (Futu 财务页)
├── 营收增速 (revenue_growth_pct)： ✅ 6/16  (Futu 有增长率的)
├── 净利润率 (net_margin_pct)：    ✅ 9/16  (推导)
├── 基石投资者 (cornerstone_*)：   ✅ 11/16 (etnet)
├── 保荐人 (sponsors)：            ⚠️ 部分  (etnet 提供 ID，名称需映射)
├── 融资倍率/孖展 (margin_*)：     ❌ 0/16  (无稳定数据源)
├── 毛利率 (gross_margin_latest)： ❌ 0/16  (需 PDF)
├── 现金流 (operating_cash_flow)： ❌ 0/16  (需 PDF)
└── 负债率 (debt_to_assets_pct)：  ❌ 0/16  (需 PDF)
```

### 数据补充操作流程

**完整取数命令**（在沙箱外运行）：
```powershell
cd C:\Users\steven\Desktop\workspace\Hong-Kong-stocks
$env:PYTHONPATH = 'src'
.venv\Scripts\python.exe -m hk_ipo_analyzer.cli daily `
  --date 2026-06-30 `
  --input-json data\verified_current_ipos_2026-06-30_futu.json `
  --skip-pdf
```

**仅用本地数据（离线）**：
```powershell
# 跳过网络抓取，仅用已有 JSON 生成报告
.venv\Scripts\python.exe -m hk_ipo_analyzer.cli daily `
  --date 2026-06-30 `
  --input-json data\verified_current_ipos_2026-06-30_futu.json `
  --skip-pdf
```

**手工补充融资孖展**：编辑 `data/manual_override.csv`，填写 `margin_multiple`、`expected_oversubscription` 等字段。


## 评分模型各维度权重

| 维度 | 满分 | 子项 | 子项上限 | 数据来源 |
|------|:----:|------|:--------:|----------|
| 公司基本面 | 25 | 营收增速 `revenue_growth_pct` | 6 | Futu 财务页 |
| | | 净利润率 `net_margin_pct` | 6 | Futu (推导: net_profit/revenue×100) |
| | | 毛利率 `gross_margin_latest` | 4 | PDF 招股书 |
| | | 现金流 `operating_cash_flow` | 4 | PDF 招股书 |
| | | 资产负债率 `debt_to_assets_pct` | 3 | PDF 招股书 |
| | | 客户集中度 `customer_concentration_top5` | 2 | PDF 招股书 |
| 行业与概念 | 15 | 赛道热度 `sector` | 5 | 规则分类器 |
| | | 行业空间 | 0 | 未启用 |
| | | 政策支持 | 0 | 未启用 |
| | | 近期同行表现 | 0 | 未启用 |
| | | 板块破发率 | 0 | 未启用 |
| 发行结构 | 15 | 募资规模 `offer_size_hkd` | 3 | etnet |
| | | 公开发售比例 `public_offer_ratio` | 3 | etnet / 招股书 |
| | | 流通结构 | 0 | 未启用 |
| | | 绿鞋机制 `greenshoe` | 2 | etnet |
| | | 保荐人 `sponsors` | 0 | 未启用 |
| | | 定价区间 | 0 | 未启用 |
| 基石投资者 | 15 | 基石数量 `cornerstone_count` | 5 | etnet |
| | | 基石占比 `cornerstone_ratio` | 4 | etnet |
| | | 基石质量 | 0 | 未启用 |
| | | 锁定期 | 0 | 未启用 |
| 市场热度 | 20 | 融资认购金额 `margin_amount_hkd` | 5 | 手动 CSV / 券商页面 |
| | | 融资倍率 `margin_multiple` | 5 | 手动 CSV / 券商页面 |
| | | 新闻关注度 `news_heat_score` | 3 | etnet / 手动 |
| | | ~~超购倍数~~ | ~~已移除~~ | 数据源不稳定 |
| | | ~~暗盘表现~~ | ~~已移除~~ | 打新期间无数据 |
| 风险扣分 | -8 | 核心字段缺失率 × 8 | -8 | 自动计算 |

> 各维度原分合计 90，缩放至 100 后扣风险分：`总分 = clamp(原分/90×100 - 风险扣分, 0, 100)`
> 2026-07-01 已从市场热度移除超购和暗盘，剩余 13 分等比放大到 20 分。

## 富途 OpenAPI 接口

### 前置条件

1. 安装富途牛牛 (FutuNiuniu) 桌面端：https://www.futunn.com/
2. 登录后，下载并启动 FutuOpenD 网关：https://openapi.futunn.com/ → 下载 OpenD 客户端
3. 安装 Python SDK：`pip install futu-api`
4. FutuOpenD 启动后默认监听 `127.0.0.1:11111`

### 已接入接口

| 接口 | 地址 (本地) | 用途 | 返回字段 |
|------|-----------|------|---------|
| `get_ipo_list` | `OpenQuoteContext.get_ipo_list(market=Market.HK)` | HK IPO 列表 | code, name, lot_size, entrance_price, ipo_price_min/max, is_subscribe_status, apply_end_time, list_time |
| `get_stock_basicinfo` | `OpenQuoteContext.get_stock_basicinfo(market=Market.HK, code_list=[code])` | 股票基本资料 | code, name, lot_size, listing_date, stock_type, exchange_type |

### 接口限制

- 仅提供基础 IPO 列表信息，**不含基石/孖展/财务/保荐人**
- `get_ipo_list` 的 `is_subscribe_status` 可确认认购开放状态
- 已上市股票的 `get_market_snapshot` / `get_capital_distribution` 有数据，但 IPO 期间全为 0
- 模块：`src/hk_ipo_analyzer/ipo_fetcher/futu_api_fetcher.py`

### 可用但未接入选用的接口

| 接口 | 说明 |
|------|------|
| `get_market_snapshot` | 市场快照 (成交量/换手率)，IPO 期间返回 0 |
| `get_capital_distribution` | 资金分布，IPO 期间返回 0 |
| `get_capital_flow` | 资金流向 |
| `get_broker_queue` | 经纪队列 |
| `get_order_book` | 买卖盘 |
## 免责声明

## 评分模型各维度权重

| 维度 | 满分 | 子项 | 子项上限 | 数据来源 |
|------|:----:|------|:--------:|----------|
| 公司基本面 | 25 | 营收增速 `revenue_growth_pct` | 6 | Futu 财务页 |
| | | 净利润率 `net_margin_pct` | 6 | Futu (推导: net_profit/revenue×100) |
| | | 毛利率 `gross_margin_latest` | 4 | PDF 招股书 |
| | | 现金流 `operating_cash_flow` | 4 | PDF 招股书 |
| | | 资产负债率 `debt_to_assets_pct` | 3 | PDF 招股书 |
| | | 客户集中度 `customer_concentration_top5` | 2 | PDF 招股书 |
| 行业与概念 | 15 | 赛道热度 `sector` | 5 | 规则分类器 |
| | | 行业空间 | 0 | 未启用 |
| | | 政策支持 | 0 | 未启用 |
| | | 近期同行表现 | 0 | 未启用 |
| | | 板块破发率 | 0 | 未启用 |
| 发行结构 | 15 | 募资规模 `offer_size_hkd` | 3 | etnet |
| | | 公开发售比例 `public_offer_ratio` | 3 | etnet / 招股书 |
| | | 流通结构 | 0 | 未启用 |
| | | 绿鞋机制 `greenshoe` | 2 | etnet |
| | | 保荐人 `sponsors` | 0 | 未启用 |
| | | 定价区间 | 0 | 未启用 |
| 基石投资者 | 15 | 基石数量 `cornerstone_count` | 5 | etnet |
| | | 基石占比 `cornerstone_ratio` | 4 | etnet |
| | | 基石质量 | 0 | 未启用 |
| | | 锁定期 | 0 | 未启用 |
| 市场热度 | 20 | 融资认购金额 `margin_amount_hkd` | 5 | 手动 CSV / 券商页面 |
| | | 融资倍率 `margin_multiple` | 5 | 手动 CSV / 券商页面 |
| | | 新闻关注度 `news_heat_score` | 3 | etnet / 手动 |
| | | ~~超购倍数~~ | ~~已移除~~ | 数据源不稳定 |
| | | ~~暗盘表现~~ | ~~已移除~~ | 打新期间无数据 |
| 风险扣分 | -8 | 核心字段缺失率 × 8 | -8 | 自动计算 |

> 各维度原分合计 90，缩放至 100 后扣风险分：`总分 = clamp(原分/90×100 - 风险扣分, 0, 100)`
> 2026-07-01 已从市场热度移除超购和暗盘，剩余 13 分等比放大到 20 分。

## 富途 OpenAPI 接口

### 前置条件

1. 安装富途牛牛 (FutuNiuniu) 桌面端：https://www.futunn.com/
2. 登录后，下载并启动 FutuOpenD 网关：https://openapi.futunn.com/ → 下载 OpenD 客户端
3. 安装 Python SDK：`pip install futu-api`
4. FutuOpenD 启动后默认监听 `127.0.0.1:11111`

### 已接入接口

| 接口 | 地址 (本地) | 用途 | 返回字段 |
|------|-----------|------|---------|
| `get_ipo_list` | `OpenQuoteContext.get_ipo_list(market=Market.HK)` | HK IPO 列表 | code, name, lot_size, entrance_price, ipo_price_min/max, is_subscribe_status, apply_end_time, list_time |
| `get_stock_basicinfo` | `OpenQuoteContext.get_stock_basicinfo(market=Market.HK, code_list=[code])` | 股票基本资料 | code, name, lot_size, listing_date, stock_type, exchange_type |

### 接口限制

- 仅提供基础 IPO 列表信息，**不含基石/孖展/财务/保荐人**
- `get_ipo_list` 的 `is_subscribe_status` 可确认认购开放状态
- 已上市股票的 `get_market_snapshot` / `get_capital_distribution` 有数据，但 IPO 期间全为 0
- 模块：`src/hk_ipo_analyzer/ipo_fetcher/futu_api_fetcher.py`

### 可用但未接入选用的接口

| 接口 | 说明 |
|------|------|
| `get_market_snapshot` | 市场快照 (成交量/换手率)，IPO 期间返回 0 |
| `get_capital_distribution` | 资金分布，IPO 期间返回 0 |
| `get_capital_flow` | 资金流向 |
| `get_broker_queue` | 经纪队列 |
| `get_order_book` | 买卖盘 |
## 免责声明

本项目及其报告仅用于个人研究和数据整理，不构成任何投资建议。港股 IPO 存在破发、流动性不足、融资成本、中签率不确定、市场波动等风险，投资者需自行判断并承担风险。

