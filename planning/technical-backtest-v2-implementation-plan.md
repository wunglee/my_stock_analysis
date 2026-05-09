# 纯技术回测 V2 实现计划

## 概述

基于 `docs/technical-backtest-v2-architecture.md` 架构设计，从零实现纯技术回测引擎，替代 v1 原型代码。

**核心原则**：垂直切片实现，每个切片可独立测试验证；TDD 优先（先写测试，再写实现）。

**目标交付物**：
- 可配置策略体系（4 个策略：双均线、MACD、RSI、布林带）
- 真实权益曲线计算（含交易费用、基准对比）
- 批量参数组回测（单股、最多 6 组参数对比）
- FastAPI 批量回测端点
- 前端接入真实后端

---

## 架构决策

1. **垂直切片而非水平分层**：按功能路径切片（信号生成 → 权益计算 → 批量回测 → API端点），每个切片可独立运行和测试
2. **TDD 优先**：每个切片先写测试（RED），再写最小实现（GREEN），最后重构（IMPROVE）
3. **Protocol + 注册表模式**：策略通过 `ITechnicalStrategy` Protocol 定义，由 `StrategyRegistry` 动态发现
4. **信号生成与权益计算解耦**：`SignalGenerator` 产出信号列表，`EquityCalculator` 基于信号模拟交易
5. **v1 原型废弃而非兼容**：直接删除 `technical_backtest_service.py` 中原型方法，不保留兼容层

---

## 依赖图

```
Signal + ITechnicalStrategy (base.py)
    │
    ├── StrategyRegistry (registry.py)
    │       │
    │       └── DualMAStrategy (dual_ma.py)
    │
    ├── SignalGenerator (signal_generator.py)
    │       │
    │       └── EquityCalculator (equity_calculator.py)
    │               │
    │               └── TradingCalendar (已有实现)
    │
    └── TechnicalBacktestService (service.py)
            │
            ├── CachingDataProviderAdapter (data_adapter.py)
            │       │
            │       └── CachingDataProvider (已有实现)
            │
            └── FastAPI Endpoints (backtest.py)
                    │
                    └── Frontend (BacktestPage.tsx)
```

**实现顺序**（从底向上，按依赖关系）：
1. 基础数据结构（Signal、Protocol）
2. 策略注册表 + 首个策略（DualMA）
3. 信号生成器
4. 权益计算器
5. 批量回测服务
6. 数据适配器
7. FastAPI 端点
8. 前端联调

---

## 任务列表

### Phase 1: 基础架构（信号 + 协议 + 注册表）

#### Task 1: 定义核心数据结构和策略协议

**描述**: 实现 `Signal` dataclass 和 `ITechnicalStrategy` Protocol，建立策略接口契约。

**验收标准**:
- [ ] `Signal` 为 frozen dataclass，含 `date`/`action`/`entry_price`/`execution_price`/`reasons` 字段
- [ ] `ITechnicalStrategy` Protocol 定义 `id`/`config`/`min_warmup_bars`/`required_columns`/`validate_params`/`generate_signals`
- [ ] `StrategyConfig`/`StrategyParameter`/`ValidationRule` dataclass 完整定义
- [ ] 文件位于 `src/services/backtest/strategies/base.py`

**验证**:
- [ ] `python -m py_compile src/services/backtest/strategies/base.py`
- [ ] 单元测试：Signal 创建和字段访问
- [ ] 单元测试：StrategyConfig 默认值和校验规则

**依赖**: None
**文件**:
- `src/services/backtest/strategies/__init__.py`
- `src/services/backtest/strategies/base.py`
- `tests/backtest/test_base.py`
**规模**: Small (1-2 files)

---

#### Task 2: 实现 StrategyRegistry 和首个策略（DualMA）

**描述**: 实现策略注册表，注册双均线策略作为首个验证策略。

**验收标准**:
- [ ] `StrategyRegistry` 支持 `register()`/`get()`/`list_all()` 操作
- [ ] `DualMAStrategy` 实现 `ITechnicalStrategy` Protocol
- [ ] `DualMAStrategy.generate_signals()` 基于短期/长期均线交叉生成 buy/sell/wait 信号
- [ ] `DualMAStrategy.validate_params()` 校验 short_period < long_period
- [ ] 配置包含 `short_period`/`long_period` 参数定义和校验规则

**验证**:
- [ ] 单元测试：注册表注册和查询
- [ ] 单元测试：DualMA 信号生成（金叉买入、死叉卖出）
- [ ] 单元测试：参数校验（short >= long 应报错）
- [ ] 单元测试：warmup bars 校验（数据不足应报错）

**依赖**: Task 1
**文件**:
- `src/services/backtest/strategies/registry.py`
- `src/services/backtest/strategies/dual_ma.py`
- `tests/backtest/test_registry.py`
- `tests/backtest/test_dual_ma.py`
**规模**: Medium (3-5 files)

---

### Checkpoint: Phase 1 完成

- [ ] 所有单元测试通过
- [ ] `python -m pytest tests/backtest/test_base.py tests/backtest/test_registry.py tests/backtest/test_dual_ma.py -v`
- [ ] 策略注册表可列出所有策略配置
- [ ] DualMA 策略可生成预期信号

---

### Phase 2: 核心计算引擎（SignalGenerator + EquityCalculator）

#### Task 3: 实现 SignalGenerator

**描述**: 实现信号生成器，代理调用策略生成信号并附加预热数据检查。

**验收标准**:
- [ ] `SignalGenerator.generate(strategy, df, params)` 返回 `list[Signal]`
- [ ] 校验 df 列包含 `strategy.required_columns`
- [ ] 校验 df 长度 >= `strategy.min_warmup_bars`
- [ ] 信号按日期升序排列
- [ ] 空信号（全 wait）情况正确处理

**验证**:
- [ ] 单元测试：正常信号生成
- [ ] 单元测试：列缺失抛出异常
- [ ] 单元测试：数据不足抛出异常
- [ ] 单元测试：空信号返回空列表

**依赖**: Task 2
**文件**:
- `src/services/backtest/engine/__init__.py`
- `src/services/backtest/engine/signal_generator.py`
- `tests/backtest/test_signal_generator.py`
**规模**: Small (1-2 files)

---

#### Task 4: 实现 EquityCalculator

**描述**: 实现权益计算器，基于信号序列模拟交易、计算费用、生成权益曲线。

**验收标准**:
- [ ] `EquityCalculator.calculate(df, signals)` 返回 `EquityResult`
- [ ] 信号执行语义：收盘生成信号，次日开盘执行（通过 TradingCalendar 查找下一交易日）
- [ ] one-position-at-a-time 仓位管理（已有持仓时忽略 buy，无持仓时忽略 sell）
- [ ] 买入费用 0.03%，卖出费用 0.13%（含印花税）
- [ ] 回测结束日强制平仓，reason 标注为 "force_close"
- [ ] 基准曲线（买入并持有）逐日计算
- [ ] `EquityResult` 含 `equity_curve`/`trades`/`total_return`/`max_drawdown`/`win_rate`/`avg_hold_days`

**验证**:
- [ ] 单元测试：单次买卖完整流程（买入 → 卖出 → 验证收益率和费用）
- [ ] 单元测试：强制平仓逻辑
- [ ] 单元测试：仓位管理（重复 buy 信号被忽略）
- [ ] 单元测试：基准曲线计算
- [ ] 单元测试：max_drawdown / win_rate / avg_hold_days 计算正确
- [ ] 单元测试：空信号（全 wait）返回初始资金曲线

**依赖**: Task 3
**文件**:
- `src/services/backtest/engine/equity_calculator.py`
- `src/services/backtest/exceptions.py`
- `tests/backtest/test_equity_calculator.py`
**规模**: Medium (3-5 files)

---

### Checkpoint: Phase 2 完成

- [ ] 所有单元测试通过
- [ ] SignalGenerator 和 EquityCalculator 独立可测试
- [ ] 端到端：给定测试数据和参数，可生成完整权益曲线和交易记录
- [ ] 费用模型计算结果与手动计算一致

---

### Phase 3: 批量回测服务层

#### Task 5: 实现 TechnicalBacktestService 和 CachingDataProviderAdapter

**描述**: 实现批量回测服务入口和数据适配器，串联信号生成和权益计算。

**验收标准**:
- [ ] `CachingDataProviderAdapter` 适配 `CachingDataProvider.get_daily_bars()` → `IDataFetcher.get_daily_data()`
- [ ] 适配器执行列名映射（`trade_date` → `date`）和排序
- [ ] `TechnicalBacktestService` 接收 `StrategyRegistry` 和 `IDataFetcher` 依赖注入
- [ ] `run_batch(request)` 对单股多参数组串行执行回测
- [ ] 每组参数返回 `ParamGroupResult`（含 status / stock_result / equity_curve / trades）
- [ ] 异常组标记为 `error`，数据不足组标记为 `insufficient_data`，不影响其他组
- [ ] 返回 `BatchResult`（含 meta + results）

**验证**:
- [ ] 单元测试：适配器列名映射和排序
- [ ] 集成测试：单参数组完整回测流程（数据获取 → 信号生成 → 权益计算 → 结果组装）
- [ ] 集成测试：多参数组批量回测（3 组参数，验证结果顺序与请求一致）
- [ ] 集成测试：异常隔离（1 组参数异常，其他组正常返回）

**依赖**: Task 4
**文件**:
- `src/services/backtest/engine/data_adapter.py`
- `src/services/backtest/service.py`
- `tests/backtest/test_data_adapter.py`
- `tests/backtest/test_service.py`
**规模**: Medium (3-5 files)

---

### Checkpoint: Phase 3 完成

- [ ] 所有单元测试和集成测试通过
- [ ] `TechnicalBacktestService.run_batch()` 可独立运行（不依赖 FastAPI）
- [ ] 批量回测结果结构符合 Schema 定义
- [ ] 端到端：给定 mock 数据，6 组参数批量回测 < 3 秒

---

### Phase 4: FastAPI 端点

#### Task 6: 实现 FastAPI 批量回测端点

**描述**: 替换 v1 原型端点，接入 V2 引擎。

**验收标准**:
- [ ] `GET /backtest/strategies` 返回策略列表（与 Schema `StrategyListResponse` 一致）
- [ ] `POST /backtest/technical/batch` 接收 `TechnicalBatchRequest`，返回 `TechnicalBatchResponse`
- [ ] 端点使用 `get_backtest_service()` 工厂函数获取服务实例
- [ ] 异常处理：StrategyNotFoundError → 400，ValueError → 400，其他 → 500
- [ ] v1 端点 `/backtest/technical` 保留（兼容），但内部可逐步迁移
- [ ] 废弃 `technical_backtest_service.py` 中原型方法（`run_backtest`、`_adjust_signals`）

**验证**:
- [ ] API 测试：`/strategies` 返回非空列表
- [ ] API 测试：`/technical/batch` 正常请求返回 200 + 完整结果
- [ ] API 测试：策略不存在返回 400
- [ ] API 测试：参数校验失败返回 400
- [ ] API 测试：单股数据不足返回 200 + `insufficient_data` 状态
- [ ] `python -m py_compile api/v1/endpoints/backtest.py`

**依赖**: Task 5
**文件**:
- `api/v1/endpoints/backtest.py`
- `api/v1/schemas/backtest.py`（已有，确认无需修改）
- `tests/api/test_backtest.py`
**规模**: Medium (3-5 files)

---

### Checkpoint: Phase 4 完成

- [ ] API 端点可通过 curl/Postman 正常调用
- [ ] 响应格式符合 Schema 定义
- [ ] 错误响应格式统一
- [ ] `./scripts/ci_gate.sh` 通过

---

### Phase 5: 前端联调

#### Task 7: 前端接入真实后端

**描述**: 前端复用 v1 界面，将 API 调用从 mock/v1 切换为 V2 真实后端。

**验收标准**:
- [ ] `useTechnicalBacktest` Hook 调用 `/technical/batch` 端点
- [ ] 参数组编辑器配置的参数正确序列化为 `ParamGroupRequest`
- [ ] 回测结果正确渲染为对比表格和权益曲线
- [ ] 错误状态（`insufficient_data`/`error`）在前端正确展示
- [ ] `window.echarts` 实例严格管理生命周期（dispose）
- [ ] AI 回测功能不受影响（隔离边界验证）

**验证**:
- [ ] E2E：选择双均线策略 → 配置 2 组参数 → 批量回测 → 结果对比图表正确渲染
- [ ] E2E：切换策略时参数组重置为默认值
- [ ] E2E：K 线数据不足时显示友好提示
- [ ] `cd apps/dsa-web && npm run build` 通过
- [ ] 手动验证：AI 回测模式仍可正常使用

**依赖**: Task 6
**文件**:
- `apps/dsa-web/src/api/backtest.ts`（确认调用路径正确）
- `apps/dsa-web/src/hooks/useTechnicalBacktest.ts`（已有，确认无需修改）
- `apps/dsa-web/src/pages/BacktestPage.tsx`（已有，确认无需修改）
**规模**: Small (1-2 files，主要是验证和微调)

---

### Checkpoint: Phase 5 完成

- [ ] 前端可正常调用 V2 后端完成批量回测
- [ ] 结果对比和权益曲线渲染正确
- [ ] AI 回测功能未受影响
- [ ] `npm run build` 通过

---

### Phase 6: 扩展策略（可选，按优先级）

#### Task 8: 实现 MACD 策略

**描述**: 基于 MACD 指标实现买卖信号生成。

**验收标准**:
- [ ] `MACDStrategy` 实现 `ITechnicalStrategy` Protocol
- [ ] 参数：fast_period / slow_period / signal_period
- [ ] 信号逻辑：MACD 线上穿信号线买入，下穿卖出
- [ ] 参数校验：fast < slow

**验证**:
- [ ] 单元测试：MACD 信号生成
- [ ] 集成测试：MACD 策略端到端回测

**依赖**: Task 2
**文件**:
- `src/services/backtest/strategies/macd.py`
- `tests/backtest/test_macd.py`
**规模**: Small (1-2 files)

---

#### Task 9: 实现 RSI 策略

**描述**: 基于 RSI 指标实现买卖信号生成。

**验收标准**:
- [ ] `RSIStrategy` 实现 `ITechnicalStrategy` Protocol
- [ ] 参数：period / overbought / oversold
- [ ] 信号逻辑：RSI 低于 oversold 买入，高于 overbought 卖出

**文件**:
- `src/services/backtest/strategies/rsi.py`
- `tests/backtest/test_rsi.py`
**规模**: Small (1-2 files)

---

#### Task 10: 实现布林带策略

**描述**: 基于布林带指标实现买卖信号生成。

**验收标准**:
- [ ] `BollingerStrategy` 实现 `ITechnicalStrategy` Protocol
- [ ] 参数：period / std_dev
- [ ] 信号逻辑：价格触及下轨买入，触及上轨卖出

**文件**:
- `src/services/backtest/strategies/bollinger.py`
- `tests/backtest/test_bollinger.py`
**规模**: Small (1-2 files)

---

### Checkpoint: Phase 6 完成

- [ ] 4 个策略全部实现并通过测试
- [ ] 注册表可列出所有 4 个策略
- [ ] 前端可切换任意策略进行回测

---

## 风险与缓解

| 风险 | 影响 | 缓解策略 |
|------|------|---------|
| `CachingDataProvider` 接口与文档假设不一致 | 高 | Task 5 中先实现适配器，如发现接口差异立即调整 |
| TradingCalendar 返回类型与 Protocol 不匹配 | 中 | Task 4 中已统一为 `pd.Timestamp`，如实际实现不一致需适配 |
| 前端 Hook 与后端 Schema 存在未发现的字段差异 | 中 | Task 7 联调时重点验证字段映射，使用 `toCamelCase` 工具处理 |
| v1 原型代码删除导致 AI 回测受影响 | 高 | Task 6 中保留 v1 端点直至 V2 验证通过，逐步迁移而非一次性删除 |
| 权益计算精度问题（浮点数累积误差） | 低 | Task 4 测试中使用 `pytest.approx` 比较浮点数结果 |

---

## 开放问题

1. **性能基线验证**：单股 6 组参数串行执行 < 3 秒的目标，需在 Task 5 集成测试中验证。如超时，考虑启用 `CachingDataProvider` 缓存或优化 EquityCalculator。
2. **费用模型精确化**：当前仅 A 股主板精确费率，港股/美股为占位值。是否需要在本阶段精确化？（建议：否，当前基线已满足回测对比需求）
3. **sessionStorage 缓存**：4.5 节标注为"规划中，尚未实现"。是否需要在本阶段实现？（建议：否，首批实现不依赖缓存）

---

## 并行化机会

- **可并行**：Task 8/9/10（3 个额外策略的实现和测试互相独立）
- **必须串行**：Task 1 → 2 → 3 → 4 → 5 → 6 → 7（存在依赖链）
- **需协调**：Phase 4（API 端点）和 Phase 5（前端联调）共享 API 契约，需先定义端点响应格式再联调

---

## 推荐实现顺序（按天）

```
第 1 天：Phase 1 — 基础架构
  - Task 1: Signal + Protocol + 数据结构
  - Task 2: Registry + DualMAStrategy
  → Checkpoint 1: 策略可生成信号

第 2 天：Phase 2 — 核心计算引擎
  - Task 3: SignalGenerator
  - Task 4: EquityCalculator
  → Checkpoint 2: 端到端权益计算验证

第 3 天：Phase 3 — 批量回测服务
  - Task 5: Service + Adapter + 集成测试
  → Checkpoint 3: 批量回测可独立运行

第 4 天：Phase 4 — API 端点
  - Task 6: FastAPI 端点 + API 测试
  → Checkpoint 4: 端点可正常调用

第 5 天：Phase 5 — 前端联调
  - Task 7: 前端接入 + E2E 验证
  → Checkpoint 5: 完整用户流程通过

第 6-7 天：Phase 6 — 扩展策略（并行）
  - Task 8/9/10: MACD + RSI + 布林带
  → Checkpoint 6: 4 策略全部可用
```
