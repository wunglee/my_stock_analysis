# 纯技术回测 V2 架构设计 — 外部评审申请

> 申请对 `docs/technical-backtest-v2-architecture.md` 进行架构评审。
> 本文档为评审申请函，非设计本身。

---

## 评审对象

- **文档**：`docs/technical-backtest-v2-architecture.md`
- **关联分析文档**：`docs/architecture.md`（第 6 节"纯技术回测引擎"）
- **关联设计文档**：`docs/technical-backtest-design.md`

## 设计范围

将纯技术回测从 v1.0（硬编码 6 种信号规则）升级为 v2.0（可配置策略体系 + 批量参数组回测），核心包括：

1. 后端：`ITechnicalStrategy` Protocol + `StrategyRegistry` + `SignalGenerator` + `EquityCalculator` 解耦架构
2. 前端：`useTechnicalBacktest` Hook + 参数组编辑器 + 纵向结果对比
3. API：`/backtest/technical/batch` 批量回测端点 + `/backtest/strategies` 策略列表端点
4. 共存：与 v1.0 AI 回测完全隔离，不破坏现有功能

## 关键设计决策（需评审）

| 编号 | 决策 | 争议点 |
|------|------|--------|
| D1 | `ITechnicalStrategy` Protocol + 注册表模式 | Protocol vs Abstract Class 的选型是否合适？ |
| D2 | 信号生成与权益计算完全解耦 | 是否过度设计？v1.0 的混合模式有何不可？ |
| D3 | 批量回测串行执行（非并行） | 单股 6 组串行是否足够快？扩展点设计是否合理？ |
| D4 | 新建 `src/backtest_v2/` 目录（不侵入现有服务） | 与渐进重构到 `src/services/` 相比，哪种演进路径更好？ |
| D5 | `Signal` 保留 v1.0 字段（`stop_loss`/`take_profit`/`confidence`） | 兼容 v1.0 但增加 v2.0 复杂度，是否值得？ |

## 自检情况

已完成自检并修复 9 项不一致问题：
- 节号重复、Schema 字段错位、不存在类引用、悬空字段等
- 详见上文修复报告

## 已知风险

1. **v1.0 迁移路径较长**：三阶段迁移（新建 v2.0 → 提取 LegacyStrategy → 清理旧代码）可能拉长技术债务周期
2. **前端 `window.echarts` 实例管理**：v2.0 使用 ECharts 渲染缩略 K 线和权益曲线，dispose 逻辑需严格验证
3. **费用模型市场差异**：当前仅支持 A 股费率（买 0.03% 卖 0.13%），港股/美股费率待扩展

## 评审重点

请评审人重点关注以下方面：

- [ ] `ITechnicalStrategy` Protocol 的接口边界是否清晰、足够通用
- [ ] `SignalGenerator` + `EquityCalculator` 解耦是否合理，通信契约是否完备
- [ ] 与 v1.0 AI 回测的隔离策略是否有遗漏的共享状态或资源冲突
- [ ] 三阶段迁移路径是否现实，有无更优的渐进式方案
- [ ] 前端 `useTechnicalBacktest` 的状态边界设计是否会导致内存泄漏或状态污染
- [ ] mermaid 类图/序列图是否准确表达设计意图

## 评审方式

请评审人阅读 `docs/technical-backtest-v2-architecture.md` 全文，在本文档下方留言评审意见，或直接提交 PR 修改建议。

---

*申请时间：2026-05-08*
*申请人：Claude Code (self-check passed)*
