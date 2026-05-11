# 纯技术回测架构设计 — 评审申请（第二轮）

> 申请对 `docs/technical-backtest-v2-architecture.md` 进行第二轮架构评审。
> 本文档为评审申请函，非设计本身。
> **状态**：已完成三轮外部评审反馈修复 + 深度可编码自检补充。

---

## 评审对象

- **文档**：`docs/technical-backtest-v2-architecture.md`
- **关联分析文档**：`docs/architecture.md`（第 6 节"纯技术回测引擎"）
- **关联设计文档**：`docs/technical-backtest-design.md`

## 设计范围

将纯技术回测从界面原型（v1 仅有 K 线图 + 前端 mock）升级为**首次真实后端实现**（可配置策略体系 + 批量参数组回测），核心包括：

1. 后端：`ITechnicalStrategy` Protocol + `StrategyRegistry` + `SignalGenerator` + `EquityCalculator` 解耦架构
2. 前端：`useTechnicalBacktest` Hook + 参数组编辑器 + 纵向结果对比
3. API：`/backtest/technical/batch` 批量回测端点 + `/backtest/strategies` 策略列表端点
4. 隔离：与 AI 回测完全隔离，不破坏现有功能

**版本定位**：v1 是界面原型（后端为 mock/exploratory 代码），本次开发是**废弃 v1 后端原型、从零重建真实回测引擎**，不是"v1 到 v2 的升级"。

## 本轮新增关键设计决策（需评审）

| 编号 | 决策 | 争议点 |
|------|------|--------|
| D6 | `StrategyConfig` / `StrategyParameter` / `ValidationRule` 完整数据结构定义 | 字段设计是否覆盖所有策略参数需求？`step` 字段是否必要？ |
| D7 | `EquityCurvePoint` / `TradeRecord` 完整数据结构定义 | 交易记录字段是否足够支持前端交易明细展示？ |
| D8 | DataFrame 列结构约定（标准化 OHLCV） | `IDataFetcher` 返回的 DataFrame 格式是否足够明确？ |
| D9 | FastAPI 端点 `async def` + `asyncio.to_thread` 模式 | CPU 密集型计算 offload 到线程池是否为最佳实践？ |
| D10 | 错误响应 JSON 格式（含部分成功场景） | `status` 字段（"success"/"insufficient_data"/"error"）设计是否合理？ |

## 自检情况

**第一轮（内部自检）**：
- 修复节号重复、Schema 字段错位、不存在类引用、悬空字段等 9 项不一致

**第二轮（基于外部评审修正）**：
- 修正版本叙事：从"v1→v2 架构升级"改为"v1 原型废弃，首次真实实现"
- 删除三阶段迁移路径，改为单阶段直接替换
- 目录命名去掉 v2 后缀：`src/services/backtest/`
- `ITechnicalStrategy` 接口扩展：`min_warmup_bars`、`required_columns`、`validate_params`
- `Signal` 字段简化：删除 `stop_loss`、`take_profit`、`confidence`；添加 `execution_price`
- Signal action 类型统一为 `Literal["buy", "sell", "wait"]`
- `profit_factor` 从 `EquityResult` 移除（YAGNI）
- `EquityCalculator` 构造函数接收 `market` 参数（预留港股/美股扩展点）
- 补充 SessionStorage 缓存策略
- 补充参数组切换 UX 说明（确认对话框 + 保留数量重置值）
- 补充 ECharts dispose 契约规范
- 修复 Mermaid 类图关系错误（删除 `SignalGenerator --> Registry`）
- 修复 Mermaid 序列图消息流向错误（`SignalGen->>Registry` → `SignalGen->>Strategy`）

**第三轮（基于最终评审修正）**：
- `EquityCalculator` 添加 `TradingCalendar` 参数，消除日期+1 的隐式假设
- `EquityCalculator` 添加 `slippage_model` 预留参数
- `TechnicalBacktestService` 强调显式依赖注入，禁止单例 fallback 模式
- 数据获取层明确复用 `CachingDataProvider`
- API router 拆分到独立文件 `technical_backtest.py`
- 回滚策略添加功能开关 `TECHNICAL_BACKTEST_ENABLED`

**第四轮（可编码深度自检补充）**：
- 补充 `StrategyConfig` / `StrategyParameter` / `ValidationRule` 完整数据结构（2.6 节）
- 补充 `EquityCurvePoint` / `TradeRecord` 完整数据结构（2.7 节）
- 补充策略注册表初始化方式（自动发现/手动注册）（2.8 节）
- 补充 DataFrame 列结构约定（标准化 OHLCV）（2.9 节）
- 补充错误响应 JSON 格式（含部分成功场景）（3.4 节）
- 补充 `useTechnicalBacktest` Hook 完整签名与使用示例（4.6 节）
- 补充 FastAPI 端点实现（`async def` + `asyncio.to_thread` + 异常类型 + 依赖注入工厂）（5.4 节）
- 补充双均线策略配置示例
- 补充首批策略清单（4 个策略的 ID/名称/类别/参数）

## 已知风险

1. **前端 `window.echarts` 实例管理**：已补充 dispose 契约规范，需在组件实现层验证
2. **费用模型市场差异**：首批仅实现 A 股费率，`market` 参数预留港股/美股扩展点
3. **参数组切换 UX**：策略切换时弹出确认对话框，需在实现层验证体验
4. **交易日历实现**：`TradingCalendar` 为 Protocol，具体实现依赖 `xcal` 或其他交易日历库
5. **数据复权**：回测假设数据已前复权，若当前数据源未复权需标注为已知限制

## 评审重点

请评审人重点关注以下方面：

- [ ] `ITechnicalStrategy` Protocol 的接口边界是否清晰、足够通用
- [ ] `SignalGenerator` + `EquityCalculator` 解耦是否合理，通信契约是否完备
- [ ] `Signal` 的 `execution_price` 设计是否消除了 `EquityCalculator` 对 `df` 的隐式依赖
- [ ] `StrategyConfig` / `StrategyParameter` / `ValidationRule` 字段设计是否覆盖所有策略参数需求
- [ ] `EquityCurvePoint` / `TradeRecord` 字段是否足够支持前端交易明细展示
- [ ] `src/services/backtest/` 目录结构是否清晰，是否符合项目现有职责分层约定
- [ ] FastAPI 端点 `async def` + `asyncio.to_thread` 模式是否为最佳实践
- [ ] 错误响应 JSON 格式（含部分成功场景）设计是否合理
- [ ] 与 AI 回测的隔离策略是否有遗漏的共享状态或资源冲突
- [ ] 前端 `useTechnicalBacktest` 的 Hook 签名是否完整，状态边界是否清晰
- [ ] ECharts dispose 契约是否足够强制，能否避免内存泄漏
- [ ] mermaid 类图/序列图/组件图是否准确表达设计意图
- [ ] **文档细节程度是否达到"可编码"标准**（一个不熟悉项目的开发者能否仅凭文档开始编码？）

## 评审方式

请评审人阅读 `docs/technical-backtest-v2-architecture.md` 全文，在本文档下方留言评审意见，或直接提交 PR 修改建议。

---

*申请时间：2026-05-08（第二轮，可编码深度自检后）*
*申请人：Claude Code（已完成四轮自检修正）*
