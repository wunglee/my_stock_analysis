# 纯技术回测架构设计 — 评审申请

> 申请对 `docs/technical-backtest-v2-architecture.md` 进行架构评审。
> 本文档为评审申请函，非设计本身。
> **状态**：基于外部评审反馈完成修正，重新提交评审。

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

## 关键设计决策（需评审）

| 编号 | 决策 | 争议点 |
|------|------|--------|
| D1 | `ITechnicalStrategy` Protocol + 注册表模式 | Protocol vs Abstract Class 的选型是否合适？ |
| D2 | 信号生成与权益计算完全解耦 | `Signal` 携带 `execution_price` 使 `EquityCalculator` 不再依赖 `df` 列结构，是否过度设计？ |
| D3 | 批量回测串行执行（非并行） | 单股 6 组串行 < 3 秒基线是否合理？ |
| D4 | `src/services/backtest/` 目录结构（无版本后缀） | `strategies/` + `engine/` + `service.py` 的分层是否清晰？ |
| D5 | `Signal` 最简设计（删除 `stop_loss`/`take_profit`/`confidence`） | 是否遗漏了未来需要的字段？ |

## 自检情况

已完成两轮自检并修复以下问题：

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

## 已知风险

1. **前端 `window.echarts` 实例管理**：已补充 dispose 契约规范，需在组件实现层验证
2. **费用模型市场差异**：首批仅实现 A 股费率，`market` 参数预留港股/美股扩展点
3. **参数组切换 UX**：策略切换时弹出确认对话框，需在实现层验证体验

## 评审重点

请评审人重点关注以下方面：

- [ ] `ITechnicalStrategy` Protocol 的接口边界是否清晰、足够通用
- [ ] `SignalGenerator` + `EquityCalculator` 解耦是否合理，通信契约是否完备
- [ ] `Signal` 的 `execution_price` 设计是否消除了 `EquityCalculator` 对 `df` 的隐式依赖
- [ ] `src/services/backtest/` 目录结构是否清晰，是否符合项目现有职责分层约定
- [ ] 与 AI 回测的隔离策略是否有遗漏的共享状态或资源冲突
- [ ] 前端 `useTechnicalBacktest` 的状态边界设计是否会导致内存泄漏或状态污染
- [ ] ECharts dispose 契约是否足够强制，能否避免内存泄漏
- [ ] mermaid 类图/序列图/组件图是否准确表达设计意图

## 评审方式

请评审人阅读 `docs/technical-backtest-v2-architecture.md` 全文，在本文档下方留言评审意见，或直接提交 PR 修改建议。

---

*申请时间：2026-05-08（修正版）*
*申请人：Claude Code（已完成两轮自检修正）*
