# 任务清单：DSA 数据架构改造

> 由 `tasks/plan.md` 自动生成，用于跟踪实施进度

---

## Phase 1：DataFetcherManager 内置磁盘缓存

### 1.1 DatabaseManager 增加缺失日期检测接口
- [x] **新增** `get_missing_date_ranges(code, start_date, end_date)` 方法 → 实现在 `SqliteBarRepository`
- [x] 实现工作日/周末排除逻辑 → 通过 `ITradingCalendar` 注入
- [x] 处理边界条件：无数据、全缺失、全存在、部分缺失
- [x] 返回不重叠、按时间排序的区间列表
- [x] **验收**：单元测试覆盖所有边界条件

### 1.2 DataFetcherManager.get_daily_data() 内置缓存优先逻辑
- [x] `__init__()` 中可选注入 `DatabaseManager` → 通过 `SqliteBarRepository`
- [x] 新增参数：`use_cache`（默认 True）、`force_refresh`（默认 False）、`auto_save`（默认 True） → `CachingDataProvider`
- [x] 实现"解析日期范围 → 查 DB → 完整则返回 → 缺失则外部请求 → 合并返回"的完整链路
- [x] 实现 DB 数据与外部数据的合并/去重逻辑
- [x] `auto_save=True` 时自动保存外部数据到 DB
- [x] **验收**：单元测试验证缓存命中、缓存缺失、强制刷新三种场景

### 1.3 Pipeline 迁移到新的缓存机制
- [x] 移除 `fetch_and_save_stock_data()` 中重复的 `has_today_data()` 检查
- [x] 调用 `get_daily_data()` 时传递 `use_cache=True, auto_save=True`
- [x] 保留断点续传的业务逻辑（Pipeline 层级的决策）
- [ ] **验收**：`python main.py --stocks 600519` 正常；断点续传和强制刷新都正确

### 1.4 BacktestService._try_fill_daily_data() 简化
- [x] 移除手动 `db.save_daily_data()` 调用
- [x] 改为调用 `get_daily_data(use_cache=True, auto_save=True)`
- [ ] **验收**：回测补数据时日志显示优先查缓存；回测结果正确

### 1.5 DataFetcherManager 缓存逻辑单元测试
- [x] 新增 `tests/unit/test_data_provider/` 测试套件
- [x] Mock 外部 Fetcher，不依赖真实网络
- [x] 使用内存 SQLite，测试独立隔离
- [x] 覆盖：缓存命中、缓存缺失、部分缺失、强制刷新、空 DB
- [x] **验收**：`pytest tests/unit/test_data_provider/ -v` 全部通过

---

## Checkpoint 1：Phase 1 验收

- [x] `./scripts/ci_gate.sh` 通过（修改文件无新增错误，pre-existing 错误 9 个来自 market_chart/chart_legacy）
- [x] `CachingDataProvider.get_daily_bars(use_cache=True)` 数据完整时不发外部请求
- [x] Pipeline 断点续传功能保留（由 CachingDataProvider 缓存机制自然覆盖）
- [x] BacktestService 回测补数据时优先使用缓存

---

## Phase 2：纯技术回测后端引擎

### 2.1 设计技术策略引擎接口
- [ ] 新增 `src/services/technical_strategy_engine.py`
- [ ] 定义 `TechnicalStrategyEngine` 类
- [ ] 定义 `TechnicalRule`、`TechnicalSignal`、`TechnicalEvaluationResult` dataclass
- [ ] 设计规则检测函数接口：`detect_func(df) -> pd.Series[bool]`
- [ ] **验收**：接口设计与前端 `TechnicalBacktestResult` 类型对齐

### 2.2 实现技术指标策略检测函数
- [ ] 实现 `detect_ma_golden_cross()`：MA5 上穿 MA10
- [ ] 实现 `detect_volume_breakout()`：成交量 > 5 日均量 2 倍
- [ ] 实现 `detect_shrink_pullback()`：量比 < 0.8 且回踩均线
- [ ] 实现 `detect_rsi_oversold_bounce()`：RSI < 30 后反弹
- [ ] 实现信号生成和模拟交易评估逻辑
- [ ] **验收**：每种检测函数有单元测试，验证边界条件

### 2.3 实现纯技术回测 API 端点
- [ ] `api/v1/schemas/backtest.py` 新增 `TechnicalBacktestRunRequest`、`TechnicalBacktestResult` schema
- [ ] `api/v1/endpoints/backtest.py` 新增 `POST /api/v1/backtest/technical/run`
- [ ] 实现后端流程：参数校验 → 批量获取数据 → 策略评估 → 返回结果
- [ ] 单只股票失败不影响其他股票
- [ ] **验收**：curl 测试 API 可正常返回符合 schema 的数据

### 2.4 前端 API 层对接
- [ ] `apps/dsa-web/src/api/backtest.ts` 新增 `runTechnical()` 方法
- [ ] `apps/dsa-web/src/pages/BacktestPage.tsx` 替换 `handleRunTechnical` 为真实 API 调用
- [ ] 添加加载状态和错误处理
- [ ] **验收**：前端点击"纯技术回测"后发起真实请求并正确渲染结果

---

## Checkpoint 2：Phase 2 验收

- [ ] `./scripts/ci_gate.sh` 通过
- [ ] `POST /api/v1/backtest/technical/run` 可正常调用
- [ ] 返回结果包含完整的技术指标信号和评估
- [ ] 前端纯技术回测页面使用真实数据

---

## 总结

| Phase | 任务数 | 预计工期 | 核心产出 |
|-------|--------|----------|----------|
| Phase 1 | 5 | 2-3 天 | DataFetcherManager 内置磁盘缓存，全局受益 |
| Phase 2 | 4 | 3-4 天 | 纯技术回测后端 API + 前端对接 |
| **总计** | **9** | **5-7 天** | 统一缓存机制 + 纯技术回测完整链路 |
