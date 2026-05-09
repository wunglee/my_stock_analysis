# DSA 数据架构深度分析报告

> 分析范围：回测功能纯技术回测链路 + 全系统数据获取机制
> 分析日期：2026-05-05

---

## 一、回测功能完整调用链路（从 /backtest 页面开始）

### 1.1 前端链路

```
BacktestPage.tsx
├── AI 回测模式
│   └── backtestApi.run({code, force, evalWindowDays, minAgeDays, limit})
│       └── POST /api/v1/backtest/run
│
└── 纯技术回测模式 (当前为 mock!)
    └── handleRunTechnical() → generateMockTechnicalResult()  ← 无后端对接
```

**关键发现**：纯技术回测目前是前端 mock 数据，`BacktestPage.tsx:560` 调用 `generateMockTechnicalResult()`，没有真实的后端 API 支持。

### 1.2 AI 回测后端链路

```
POST /api/v1/backtest/run
└── BacktestService.run_backtest()
    ├── BacktestRepository.get_candidates()     → 获取待回测的 AnalysisHistory 记录
    │
    └── 对每个候选记录循环：
        ├── StockRepository.get_start_daily()   → 查 SQLite 找分析日期的收盘价
        │   └── 数据不存在？
        │       └── BacktestService._try_fill_daily_data()
        │           └── DataFetcherManager.get_daily_data()  → 外部请求
        │               └── 获取成功 → db.save_daily_data()   → 存入 SQLite
        │
        ├── StockRepository.get_forward_bars()  → 查 SQLite 找后续 N 天数据
        │   └── 数据不足？
        │       └── 再次 _try_fill_daily_data() → 外部请求 → 存入 SQLite
        │
        └── BacktestEngine.evaluate_single()    → 纯逻辑评估（DB 无关）
            └── 结果 → BacktestRepository.save_results_batch()
```

### 1.3 日常分析流水线数据链路

```
StockAnalysisPipeline.fetch_and_save_stock_data()
├── db.has_today_data(code, target_date)       → 检查断点续传
│   └── 有数据且非强制刷新？→ 直接返回 True（跳过网络请求）
│
└── 无数据或强制刷新：
    ├── fetcher_manager.get_daily_data(code, days=30)
    │   └── DataFetcherManager 按优先级遍历多源 Fetcher
    │       ├── EfinanceFetcher._fetch_raw_data() → _normalize_data()
    │       ├── AkshareFetcher._fetch_raw_data() → _normalize_data()
    │       ├── ...（自动故障切换）
    │       └── 返回 (DataFrame, source_name)
    │
    └── db.save_daily_data(df, code, source_name)  → UPSERT 到 SQLite
```

---

## 二、当前系统数据存储现状

### 2.1 数据库结构（SQLite + SQLAlchemy ORM）

```
DatabaseManager（单例）
├── stock_daily 表          ← 日线数据（OHLCV + 技术指标）
│   ├── code + date 联合唯一约束
│   ├── open/high/low/close/volume/amount/pct_chg
│   ├── ma5/ma10/ma20/volume_ratio（本地计算的技术指标）
│   └── data_source 字段记录数据来源
│
├── analysis_history 表     ← 分析历史记录
├── backtest_results 表     ← 回测结果
├── backtest_summaries 表   ← 回测汇总
├── news_intel 表           ← 新闻情报
├── fundamental_snapshot 表 ← 基本面快照
└── ...（其他业务表）
```

### 2.2 数据保存机制

**已实现**：
- `DatabaseManager.save_daily_data()`：按 `(code, date)` 批量 UPSERT
- SQLite 分支使用 `INSERT ... ON CONFLICT DO UPDATE`（chunk=50）
- 记录 `data_source` 字段追溯数据来源
- Pipeline 的 `fetch_and_save_stock_data()` 在分析主流程中自动保存
- BacktestService 的 `_try_fill_daily_data()` 在回测补数据时自动保存

### 2.3 数据查询机制

**StockRepository 封装**：
- `get_start_daily(code, analysis_date)`：获取分析日期（或最近前序日期）的数据
- `get_forward_bars(code, analysis_date, eval_window_days)`：获取后续 N 天数据
- `get_range(code, start_date, end_date)`：获取日期范围数据
- `get_latest(code, days)`：获取最近 N 天数据

---

## 三、多源数据源架构（已存在）

### 3.1 Fetcher 策略模式

```
BaseFetcher（抽象基类）
├── _fetch_raw_data()       → 子类实现：从具体数据源获取原始数据
├── _normalize_data()       → 子类实现：统一列名标准化
├── _clean_data()           → 通用：类型转换、去空值、排序
├── _calculate_indicators() → 通用：计算 MA5/MA10/MA20/Volume_Ratio
└── get_daily_data()        → 统一入口：raw → normalize → clean → indicators

DataFetcherManager（策略管理器）
├── 管理 7 个 Fetcher 实例，按 priority 排序
├── get_daily_data()        → 按优先级自动故障切换
├── get_realtime_quote()    → 实时行情 + 字段补充
├── get_chip_distribution() → 筹码分布 + 熔断器保护
├── get_stock_name()        → 股票名称 + 缓存
└── get_fundamental_context() → 基本面数据聚合
```

### 3.2 数据源优先级（按市场）

| 市场 | 优先级链 | 特殊处理 |
|------|---------|---------|
| A股 | Efinance(P0) → AkShare(P1) → Tushare(P0/2) → Pytdx(P2) → Baostock(P3) | 涨跌停规则区分 |
| 港股 | Longbridge → AkShare(hk) | 代码格式 HK00700 |
| 美股 | YFinance → Longbridge | 指数映射 SPX→^GSPC |

### 3.3 防故障机制

- **自动故障切换**：单源失败自动尝试下一源
- **熔断器**：实时行情连续3次失败熔断5分钟；筹码连续2次失败熔断10分钟
- **字段补充**：主源成功但缺少量比/换手率时，从后续源补充
- **防封禁**：随机休眠(1.5-5秒)、随机 User-Agent、tenacity 指数退避重试

---

## 四、核心问题诊断

### 问题 1：DataFetcherManager 没有内置磁盘缓存优先机制 ✅ 关键缺失

**现状**：
- `DataFetcherManager.get_daily_data()` **总是直接走外部请求**
- 磁盘缓存检查（`has_today_data`）只在**上层调用者**（Pipeline/BacktestService）中实现
- 各调用点重复实现"先查 DB → 再查外部"的逻辑

**影响**：
- 任何直接调用 `DataFetcherManager.get_daily_data()` 的代码都会忽略本地缓存
- 回测补数据 `_try_fill_daily_data()` 每次都会发起外部请求
- 无法统一控制缓存策略（TTL、刷新策略等）

**代码证据**：
```python
# data_provider/base.py:902-1037
# DataFetcherManager.get_daily_data() 直接遍历 fetcher，没有查 DB 逻辑

# src/core/pipeline.py:211
# Pipeline 自己实现：if not force_refresh and self.db.has_today_data(code): return

# src/services/backtest_service.py:347-364
# BacktestService 自己实现：_try_fill_daily_data() 直接调 manager.get_daily_data()
```

### 问题 2：纯技术回测没有后端实现

**现状**：前端 mock 数据，后端无对应 API。

**影响**：纯技术回测功能不可用，用户只能使用基于 AI 分析历史的回测。

### 问题 3：缓存策略不统一

**现状**：
- Pipeline：用 `has_today_data()` 检查，以"自然日"为粒度（周末也会返回 False）
- BacktestService：没有缓存检查，直接外部请求
- DataFetcherManager：只有内存缓存（实时行情 10 分钟 TTL、基本面 256 条 TTL）

---

## 五、设计方案讨论

### 目标回顾

1. DataProvider 底层获取对接多源数据源 → **已基本做到，DataFetcherManager 已有 7 源自动切换**
2. 多源数据存入本地数据库 → **已做到，Pipeline 和 BacktestService 都有 save_daily_data()**
3. DataProvider 负责磁盘缓存（先查磁盘→不全则补→返回） → **未做到，这是核心改进点**

### 方案 A：DataFetcherManager 内置磁盘缓存（推荐）

**思路**：在 `DataFetcherManager.get_daily_data()` 中内置"先查本地 DB → 缺失则外部请求 → 外部返回后保存 DB"的完整缓存链路。

**改动点**：
1. `DataFetcherManager.__init__()` 中注入 `DatabaseManager`（可选，默认从单例获取）
2. `get_daily_data()` 增加 `use_cache: bool = True` 参数
3. 方法内部先查 `db.get_data_range()` / `db.get_latest_data()`
4. 若数据完整（覆盖请求的日期范围），直接返回
5. 若数据不完整，计算缺失区间，调用现有 Fetcher 链补全
6. 补全后 `save_daily_data()`，然后返回完整数据

**优点**：
- 一处实现，全局受益（Pipeline、BacktestService、未来新模块）
- 调用者不再需要自己实现缓存检查逻辑
- 缓存策略统一管理（TTL、刷新、force 等）

**缺点**：
- DataFetcherManager 目前不依赖 DB，引入后耦合度增加
- 需要处理"部分数据在 DB，部分需要外部补"的合并逻辑
- 回测场景可能需要特定日期的精确数据，缓存粒度需要精细设计

### 方案 B：新增 CachedDataFetcher 装饰器/中间件

**思路**：保持 DataFetcherManager 不变，新增一个 `CachedDataFetcherManager` 子类或包装器。

**改动点**：
1. 新建 `data_provider/cached_manager.py`
2. `CachedDataFetcherManager(DataFetcherManager)` 子类
3. 重写 `get_daily_data()`，在 super().get_daily_data() 前后加缓存逻辑
4. Pipeline 和 BacktestService 改用 CachedDataFetcherManager

**优点**：
- 不改动现有 DataFetcherManager，风险低
- 缓存逻辑和获取逻辑完全解耦
- 易于测试（可以 mock DB）

**缺点**：
- 多了一个抽象层
- 需要修改所有调用点才能生效

### 方案 C：Repository 层增加缓存透明接口

**思路**：在 `StockRepository` 中增加一个"透明获取"方法，隐藏缓存细节。

**改动点**：
1. `StockRepository.get_daily_data_with_fetch()` 新方法
2. 内部先查 DB，缺失则调 DataFetcherManager，获取后保存
3. BacktestService 使用 Repository 新方法
4. Pipeline 也迁移到 Repository 层

**优点**：
- 符合 Repository Pattern 设计
- 业务逻辑不直接依赖 DataFetcherManager

**缺点**：
- Repository 目前只封装 DB 操作，引入外部获取会改变其职责边界
- Pipeline 目前直接调用 fetcher_manager，改动面大

### 方案 D：纯技术回测后端实现（独立设计）

纯技术回测需要：
1. 接收股票代码列表、起止日期、评估窗口
2. 获取每只股票在日期范围内的完整 K 线数据
3. 应用纯技术指标策略（MA 金叉、放量突破等）
4. 生成买入/卖出信号
5. 模拟交易并计算收益
6. 返回结果

**数据源依赖**：
- 需要大量使用历史 K 线数据 → 正好可以利用上述磁盘缓存机制
- 若缓存完善，纯技术回测可以快速从本地 DB 获取大量历史数据

---

## 六、建议的推进顺序

```
Phase 1: DataFetcherManager 内置磁盘缓存（方案 A 或 B）
    → 解决核心问题：统一缓存优先的数据获取

Phase 2: 纯技术回测后端 API 实现
    → 基于 Phase 1 的缓存机制，高效获取历史数据
    → 实现技术指标策略引擎

Phase 3: 前端对接真实 API
    → 替换 generateMockTechnicalResult()
```

---

## 七、待讨论问题

1. **缓存粒度**：按自然日缓存还是按交易日缓存？周末/节假日是否需要特殊处理？
2. **数据新鲜度**：磁盘缓存的 TTL 策略是什么？实时分析 vs 回测历史分析是否有不同的刷新策略？
3. **多源冲突**：同一股票同一日期，不同数据源可能有微小差异（复权口径不同），如何处理？
4. **纯技术回测策略**：需要实现哪些技术指标策略？是否与现有的 YAML 策略体系（strategies/）打通？
5. **回测数据量**：纯技术回测可能需要拉取大量历史数据（多只股票 x 多年），是否需要批量/异步获取优化？
