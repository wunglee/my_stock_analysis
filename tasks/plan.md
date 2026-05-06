# DSA 数据架构改造计划

> 目标：统一磁盘缓存优先的数据获取 + 纯技术回测后端实现
> 基于：`docs/data_architecture_analysis.md`

---

## 一、组件依赖图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端层                                           │
│  BacktestPage.tsx                                                           │
│  ├── AI 回测模式 ──→ backtestApi.run() ──→ POST /api/v1/backtest/run       │
│  └── 纯技术回测 ──→ 【当前为 MOCK，需后端实现】                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API 层 (FastAPI)                                │
│  api/v1/endpoints/backtest.py                                               │
│  ├── POST /run ──→ BacktestService.run_backtest()                          │
│  ├── GET /results                                                          │
│  ├── GET /performance                                                      │
│  └── 【新增】POST /technical/run ──→ TechnicalBacktestService.run()        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              服务层                                           │
│  src/services/                                                              │
│  ├── backtest_service.py        BacktestService                             │
│  │   ├── run_backtest()                                                     │
│  │   │   ├── repo.get_candidates()                                          │
│  │   │   ├── stock_repo.get_start_daily()                                   │
│  │   │   ├── stock_repo.get_forward_bars()                                  │
│  │   │   ├── _try_fill_daily_data() ──→ DataFetcherManager.get_daily_data()│
│  │   │   └── BacktestEngine.evaluate_single()                               │
│  │   └── 【简化】_try_fill_daily_data() ──→ manager.get_daily_data()       │
│  │                                              (缓存逻辑内聚到 Manager)      │
│  └── 【新增】technical_backtest_service.py                                   │
│       └── run() ──→ TechnicalStrategyEngine.evaluate()                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据层                                           │
│  src/repositories/              src/storage.py (DatabaseManager)            │
│  ├── stock_repo.py              ├── StockDaily (OHLCV + 技术指标)            │
│  │   ├── get_start_daily()      ├── save_daily_data()  UPSERT               │
│  │   ├── get_forward_bars()     ├── get_data_range()                        │
│  │   └── get_range()            ├── get_latest_data()                       │
│  ├── backtest_repo.py           ├── has_today_data()                        │
│  └── 【可选】stock_repo.get_daily_data_with_fetch()                         │
│                                  └── 【新增】get_missing_date_ranges()       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据获取层 (核心改造区)                           │
│  data_provider/base.py                                                      │
│  DataFetcherManager                                                         │
│  ├── 【改造前】get_daily_data() ──→ 直接遍历外部 Fetcher                     │
│  ├── 【改造后】get_daily_data()                                            │
│  │   ├── 1. 解析请求日期范围                                                │
│  │   ├── 2. 查询本地 DB (get_data_range / has_today_data)                   │
│  │   ├── 3. 若数据完整 ──→ 直接返回                                         │
│  │   ├── 4. 若数据缺失 ──→ 计算缺失区间 ──→ 外部请求                        │
│  │   ├── 5. 外部返回后 ──→ db.save_daily_data()                            │
│  │   └── 6. 合并 DB 数据 + 外部数据 ──→ 返回                               │
│  ├── get_realtime_quote()                                                   │
│  ├── get_chip_distribution()                                                │
│  └── get_stock_name()                                                       │
│                                                                             │
│  BaseFetcher (7 个子类)                                                     │
│  ├── EfinanceFetcher    (P0, A股首选)                                       │
│  ├── AkshareFetcher     (P1, A股)                                           │
│  ├── TushareFetcher     (P0/2, A股)                                         │
│  ├── PytdxFetcher       (P2, 通达信)                                        │
│  ├── BaostockFetcher    (P3, A股)                                           │
│  ├── YfinanceFetcher    (P4, 美股/指数)                                     │
│  └── LongbridgeFetcher  (P5, 美股/港股兜底)                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              流水线层                                         │
│  src/core/pipeline.py                                                       │
│  StockAnalysisPipeline                                                      │
│  ├── 【改造前】fetch_and_save_stock_data()                                  │
│  │   ├── self.db.has_today_data()  ← 自己实现缓存检查                        │
│  │   ├── self.fetcher_manager.get_daily_data()  ← 总是外部请求               │
│  │   └── self.db.save_daily_data()                                          │
│  └── 【改造后】fetch_and_save_stock_data()                                  │
│       ├── 移除 has_today_data() 检查（Manager 内部处理）                     │
│       ├── manager.get_daily_data(force=force_refresh)                       │
│       └── 【若 Manager 不自动 save，保留 save_daily_data】                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、垂直切片设计

**原则**：每个切片是一个完整的端到端功能路径，可独立开发、测试、验证。

### 切片 1：DataFetcherManager 内置磁盘缓存（核心基础设施）

这是最底层的基础设施改造，所有上层功能都依赖它。

**覆盖路径**：
`Pipeline.fetch_and_save_stock_data()` → `DataFetcherManager.get_daily_data()` → `DatabaseManager.save_daily_data()`
`BacktestService._try_fill_daily_data()` → `DataFetcherManager.get_daily_data()` → `DatabaseManager.save_daily_data()`

### 切片 2：纯技术回测后端引擎

基于切片 1 的缓存能力，实现纯技术指标策略的回测引擎和 API。

**覆盖路径**：
`BacktestPage.tsx` → `POST /api/v1/backtest/technical/run` → `TechnicalBacktestService.run()` → `TechnicalStrategyEngine.evaluate()` → `DataFetcherManager.get_daily_data()`

### 切片 3：前端对接真实 API

替换前端 mock，连接后端真实接口。

**覆盖路径**：
`BacktestPage.tsx:handleRunTechnical` → `backtestApi.runTechnical()` → 渲染真实结果

---

## 三、Phase 1 详细任务：DataFetcherManager 内置磁盘缓存

### 任务 1.1：DatabaseManager 增加缺失日期检测接口

**文件**：`src/storage.py`

**目标**：为 DataFetcherManager 提供"给定日期范围，返回缺失区间"的能力。

**新增方法**：

```python
def get_missing_date_ranges(
    self,
    code: str,
    start_date: date,
    end_date: date,
) -> List[Tuple[date, date]]:
    """
    返回给定日期范围内，数据库中缺失数据的连续区间列表。
    
    逻辑：
    1. 查询 DB 中该股票在 [start_date, end_date] 内已有的所有交易日
    2. 与期望的交易日序列对比（仅考虑工作日，去除已知节假日）
    3. 返回缺失的连续区间列表 [(missing_start, missing_end), ...]
    
    注意：
    - 若 start_date > end_date，返回空列表
    - 若 DB 中无该股票任何数据，返回 [(start_date, end_date)]
    - 周末/节假日不需要数据，不计入缺失
    """
```

**验收标准**：
- [ ] 方法签名包含完整的 type hints 和 docstring
- [ ] 正确处理周末和节假日（至少排除周六日）
- [ ] 正确处理边界条件（无数据、全部缺失、全部存在、部分缺失）
- [ ] 返回的区间不重叠、按时间顺序排列
- [ ] 单元测试覆盖所有边界条件

**验证步骤**：
1. 在测试数据库中插入部分日期数据
2. 调用 `get_missing_date_ranges()` 验证返回结果
3. 对比期望的缺失区间与实际返回

---

### 任务 1.2：DataFetcherManager.get_daily_data() 内置缓存优先逻辑

**文件**：`data_provider/base.py`

**目标**：在 `get_daily_data()` 中内置"先查本地 DB → 缺失则外部请求 → 合并后返回"的完整缓存链路。

**改动点**：

1. `DataFetcherManager.__init__()` 中可选注入 `DatabaseManager`（默认从单例获取）
2. `get_daily_data()` 增加参数：
   ```python
   def get_daily_data(
       self,
       stock_code: str,
       start_date: Optional[str] = None,
       end_date: Optional[str] = None,
       days: int = 30,
       *,
       use_cache: bool = True,        # 新增：是否使用磁盘缓存
       force_refresh: bool = False,   # 新增：是否强制刷新（忽略缓存）
       auto_save: bool = True,        # 新增：外部获取后是否自动保存
   ) -> Tuple[pd.DataFrame, str]:
   ```
3. 方法内部新增缓存逻辑：
   ```
   if use_cache and not force_refresh:
       1. 解析请求的日期范围 (start_date, end_date, days → resolved_start, resolved_end)
       2. 查询 DB: db.get_data_range(code, resolved_start, resolved_end)
       3. 检查数据是否完整（覆盖所有期望的交易日）
       4. 若完整 → 直接返回 DB 数据，source="cache"
       5. 若缺失 → 计算缺失区间 missing_ranges
       6. 调用外部 Fetcher 获取缺失区间（或整个范围，取决于实现）
       7. 若 auto_save → db.save_daily_data(df_external, code, source)
       8. 合并 DB 数据 + 外部数据 → 去重 → 排序 → 返回
   else:
       走原有逻辑（直接外部请求）
   ```

**关键决策点**：
- **缓存粒度**：按交易日（排除周末），对 A 股不处理节假日（简化第一版）
- **数据新鲜度**：不设置 TTL（默认信任本地数据），通过 `force_refresh=True` 刷新
- **多源冲突**：同一 `(code, date)` 已有数据时，外部新数据 UPSERT 覆盖（保留 `data_source` 字段记录最新来源）
- **合并策略**：DB 数据与外部数据按 `(code, date)` 去重，外部数据优先级更高

**验收标准**：
- [ ] `get_daily_data()` 新增 `use_cache`、`force_refresh`、`auto_save` 参数，默认行为向后兼容
- [ ] 当 `use_cache=True` 且数据完整时，不发起任何外部请求
- [ ] 当 `use_cache=True` 且数据缺失时，仅请求缺失部分（或合理的最小范围）
- [ ] 当 `force_refresh=True` 时，忽略缓存直接走外部请求
- [ ] 外部获取成功后，若 `auto_save=True`，自动保存到 DB
- [ ] 返回的 DataFrame 包含完整的请求日期范围
- [ ] 所有现有调用点行为不变（默认参数保持原有行为）

**验证步骤**：
1. 准备测试：先往 DB 写入一只股票的部分历史数据
2. 调用 `get_daily_data(code, use_cache=True)` → 验证无外部请求、返回 DB 数据
3. 调用 `get_daily_data(code, use_cache=True)` 请求更大范围 → 验证仅请求缺失部分
4. 调用 `get_daily_data(code, force_refresh=True)` → 验证走外部请求
5. 验证 DB 中数据已更新

---

### 任务 1.3：Pipeline 迁移到新的缓存机制

**文件**：`src/core/pipeline.py`

**目标**：移除 Pipeline 中重复的缓存检查逻辑，委托给 DataFetcherManager。

**当前逻辑**：
```python
def fetch_and_save_stock_data(self, code, force_refresh=False, ...):
    target_date = self._resolve_resume_target_date(code, ...)
    if not force_refresh and self.db.has_today_data(code, target_date):
        return True, None  # 自己检查缓存
    df, source_name = self.fetcher_manager.get_daily_data(code, days=30)  # 总是外部
    saved_count = self.db.save_daily_data(df, code, source_name)
```

**改造后逻辑**：
```python
def fetch_and_save_stock_data(self, code, force_refresh=False, ...):
    target_date = self._resolve_resume_target_date(code, ...)
    # 断点续传检查仍保留（Pipeline 层级的业务决策）
    if not force_refresh and self.db.has_today_data(code, target_date):
        return True, None
    
    # Manager 内部处理缓存和保存
    df, source_name = self.fetcher_manager.get_daily_data(
        code, days=30,
        use_cache=True,
        force_refresh=force_refresh,
        auto_save=True,
    )
    
    # 若 Manager 没有 auto_save，保留 save 逻辑
    # saved_count = self.db.save_daily_data(df, code, source_name)
    return True, None
```

**验收标准**：
- [ ] Pipeline 的断点续传行为不变
- [ ] 当 `force_refresh=False` 且数据已存在时，跳过网络请求
- [ ] 当 `force_refresh=True` 时，强制刷新
- [ ] 网络请求次数不增加（相比改造前）

**验证步骤**：
1. 运行 `python main.py --stocks 600519 --dry-run` 验证正常
2. 断点续传场景：再次运行同一股票，验证跳过网络请求
3. force_refresh 场景：`--stocks 600519 --force` 验证重新获取

---

### 任务 1.4：BacktestService._try_fill_daily_data() 简化

**文件**：`src/services/backtest_service.py`

**目标**：`_try_fill_daily_data()` 不再需要自己保存数据，Manager 内部处理。

**当前逻辑**：
```python
def _try_fill_daily_data(self, *, code, analysis_date, eval_window_days):
    manager = DataFetcherManager()
    df, source = manager.get_daily_data(stock_code=code, ...)  # 总是外部
    if df is not None and not df.empty:
        self.db.save_daily_data(df, code=code, data_source=source)
```

**改造后逻辑**：
```python
def _try_fill_daily_data(self, *, code, analysis_date, eval_window_days):
    manager = DataFetcherManager()
    df, source = manager.get_daily_data(
        stock_code=code, ...,
        use_cache=True,
        auto_save=True,
    )
    # 不再需要手动 save，Manager 内部已处理
```

**验收标准**：
- [ ] `_try_fill_daily_data()` 逻辑简化，不再直接调用 `db.save_daily_data()`
- [ ] 回测补数据时优先使用本地缓存
- [ ] 回测整体流程正常

**验证步骤**：
1. 触发回测：POST /api/v1/backtest/run
2. 观察日志：验证补数据时优先查 DB，而非直接外部请求
3. 验证回测结果正确

---

### 任务 1.5：DataFetcherManager 缓存逻辑单元测试

**文件**：`tests/unit/test_data_fetcher_cache.py`（新增）

**测试范围**：
- `get_daily_data(use_cache=True)` 数据完整时直接返回缓存
- `get_daily_data(use_cache=True)` 数据缺失时请求外部并合并
- `get_daily_data(force_refresh=True)` 忽略缓存
- 多源数据合并时的去重逻辑
- 边界条件：空 DB、部分数据、全部数据

**验收标准**：
- [ ] 测试覆盖新增缓存逻辑的所有分支
- [ ] Mock 外部 Fetcher，不依赖真实网络
- [ ] 使用内存 SQLite，测试独立隔离

---

## 四、Phase 2 详细任务：纯技术回测后端引擎

### 任务 2.1：设计技术策略引擎接口

**文件**：`src/services/technical_strategy_engine.py`（新增）

**目标**：定义纯技术指标策略的评估引擎，支持从 `strategies/*.yaml` 加载规则。

**核心接口**：

```python
class TechnicalStrategyEngine:
    """
    纯技术指标策略引擎
    
    职责：
    1. 从 strategies/*.yaml 加载技术指标规则
    2. 对给定股票的 K 线数据应用规则，生成买入/卖出信号
    3. 模拟交易并计算收益
    """
    
    def evaluate(
        self,
        code: str,
        kline_data: pd.DataFrame,  # 完整的 OHLCV 数据
        rules: List[TechnicalRule],  # 要应用的规则列表
        eval_window_days: int = 10,
    ) -> TechnicalEvaluationResult:
        ...

@dataclass
class TechnicalRule:
    name: str           # 规则名称，如 "MA金叉"
    condition: str      # 条件描述
    detect_func: Callable[[pd.DataFrame], pd.Series]  # 检测函数，返回布尔序列

@dataclass  
class TechnicalSignal:
    date: date
    action: str  # buy / sell / hold / wait
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    reasons: List[str]
    confidence: float

@dataclass
class TechnicalEvaluationResult:
    code: str
    stock_name: str
    date_range: Tuple[str, str]
    total_signals: int
    win_rate: float
    avg_return: float
    max_drawdown: float
    rules: List[Dict[str, Any]]
    signals: List[TechnicalSignal]
    evaluations: List[Dict[str, Any]]
```

**验收标准**：
- [ ] 接口设计清晰，与前端 `TechnicalBacktestResult` 类型对齐
- [ ] 规则检测函数可扩展，支持新增策略
- [ ] 第一版支持至少 3 种策略：MA金叉、放量突破、缩量回调

---

### 任务 2.2：实现技术指标策略检测函数

**文件**：`src/services/technical_strategy_engine.py`

**目标**：实现具体的指标检测逻辑。

**检测函数列表**：

1. **MA5/MA10 金叉检测**
   ```python
   def detect_ma_golden_cross(df: pd.DataFrame) -> pd.Series:
       # MA5 在最近 3 个交易日内上穿 MA10
       ...
   ```

2. **放量突破检测**
   ```python
   def detect_volume_breakout(df: pd.DataFrame) -> pd.Series:
       # 成交量 > 5 日均量 2 倍，且价格创近期新高
       ...
   ```

3. **缩量回调检测**
   ```python
   def detect_shrink_pullback(df: pd.DataFrame) -> pd.Series:
       # 量比 < 0.8，价格回踩 MA5/MA10
       ...
   ```

4. **RSI 超卖反弹检测**
   ```python
   def detect_rsi_oversold_bounce(df: pd.DataFrame) -> pd.Series:
       # RSI < 30 后反弹
       ...
   ```

**验收标准**：
- [ ] 每种检测函数有明确的数学定义
- [ ] 使用 pandas 向量化运算，性能可接受
- [ ] 单元测试验证每种检测函数的正确性

---

### 任务 2.3：实现纯技术回测 API 端点

**文件**：
- `api/v1/endpoints/backtest.py`（新增路由）
- `api/v1/schemas/backtest.py`（新增 schema）

**目标**：提供 `POST /api/v1/backtest/technical/run` 端点。

**请求 Schema**：
```python
class TechnicalBacktestRunRequest(BaseModel):
    codes: List[str] = Field(..., description="股票代码列表")
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    eval_window_days: int = Field(10, ge=1, le=120)
    rules: Optional[List[str]] = Field(None, description="指定规则名称，None=全部")
```

**响应 Schema**：与前端 `TechnicalBacktestResult` 对齐。

**后端流程**：
```
POST /api/v1/backtest/technical/run
├── 1. 参数校验
├── 2. 对每只股票：
│   ├── DataFetcherManager.get_daily_data(code, start_date, end_date, use_cache=True)
│   ├── TechnicalStrategyEngine.evaluate(code, df, rules, eval_window_days)
│   └── 收集结果
├── 3. 计算跨股票相关性（可选）
└── 4. 返回 TechnicalBacktestResult
```

**验收标准**：
- [ ] API 端点可正常调用
- [ ] 参数校验完整（日期格式、code 合法性）
- [ ] 错误处理：单只股票失败不影响其他股票
- [ ] 响应结构与前端类型定义一致

---

### 任务 2.4：前端 API 层对接

**文件**：
- `apps/dsa-web/src/api/backtest.ts`（新增方法）
- `apps/dsa-web/src/pages/BacktestPage.tsx`（替换 mock）

**目标**：
1. 在 `backtestApi` 中新增 `runTechnical()` 方法
2. `BacktestPage.tsx` 中 `handleRunTechnical` 调用真实 API

**验收标准**：
- [ ] 点击"纯技术回测"按钮后，发起真实 API 请求
- [ ] 加载状态正确显示
- [ ] 错误处理：API 失败时显示错误信息
- [ ] 结果正确渲染（与 mock 数据格式一致）

---

## 五、Phase 3：检查点与验收

### 检查点 1：Phase 1 完成后

**验证清单**：
- [ ] `DataFetcherManager.get_daily_data(use_cache=True)` 数据完整时不发外部请求
- [ ] Pipeline 断点续传功能正常
- [ ] BacktestService 回测补数据时优先使用缓存
- [ ] 所有单元测试通过
- [ ] `./scripts/ci_gate.sh` 通过

### 检查点 2：Phase 2 完成后

**验证清单**：
- [ ] `POST /api/v1/backtest/technical/run` 可正常调用
- [ ] 返回结果包含完整的技术指标信号和评估
- [ ] 支持至少 3 种策略的检测
- [ ] 前端纯技术回测页面使用真实数据
- [ ] `./scripts/ci_gate.sh` 通过

---

## 六、风险与回滚策略

| 风险 | 影响 | 缓解措施 | 回滚方式 |
|------|------|----------|----------|
| DataFetcherManager 缓存逻辑引入 bug | 所有数据获取路径受影响 | 1. 默认参数保持向后兼容<br>2. 灰度：先在新方法测试<br>3. 保留旧方法作为 fallback | 回滚到 `use_cache=False` 默认值 |
| 缓存数据与外部数据不一致 | 分析结果偏差 | 1. `force_refresh` 参数<br>2. `data_source` 字段记录来源<br>3. 定期全量刷新机制 | 手动清理缓存 + 强制刷新 |
| 纯技术回测策略检测不准确 | 回测结果不可信 | 1. 第一版使用成熟指标（MA、成交量）<br>2. 单元测试覆盖边界条件<br>3. 与已知结果对比验证 | 前端保留 mock 开关作为 fallback |
| 性能退化 | 缓存查询增加 DB 开销 | 1. 日期范围查询有索引<br>2. 缓存命中时省去网络延迟<br>3. 监控实际耗时 | 禁用缓存，回退到直连外部 |

---

## 七、开放决策（需用户确认）

1. **缓存粒度**：
   - 选项 A：仅排除周末（简单，第一版推荐）
   - 选项 B：排除 A 股法定节假日（需要节假日日历）
   - 选项 C：以 DB 中实际存在的数据为基准，不预设交易日（最灵活）

2. **DataFetcherManager 是否自动 save**：
   - 选项 A：`auto_save=True` 默认开启，Manager 内部自动保存（推荐，逻辑内聚）
   - 选项 B：`auto_save=False` 默认，调用者自己决定保存时机（更灵活，但代码分散）

3. **纯技术回测策略范围**：
   - 选项 A：第一版只做 MA 金叉、放量突破、缩量回调 3 种（最小可用）
   - 选项 B：同时加载 `strategies/*.yaml` 中定义的所有技术指标策略（更全面，但复杂度更高）

4. **方案选择**：
   - 推荐：方案 A（DataFetcherManager 内置磁盘缓存）+ 方案 D（纯技术回测后端独立实现）
   - 是否同意此组合？
