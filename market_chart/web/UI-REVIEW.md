# UI Review — ExplorerPage 架构与视觉审查

> 审查范围：`src/pages/ExplorerPage.tsx` 及其直接子组件  
> 审查日期：2026-04-24  
> 审查依据：6 支柱标准（Copywriting / Visuals / Color / Typography / Spacing / Experience Design）

---

## 评分总览

| 支柱 | 得分 | 权重 |
|------|------|------|
| Copywriting | 2/4 | 低 |
| Visuals | 2/4 | 高 |
| Color | 3/4 | 中 |
| Typography | 2/4 | 中 |
| Spacing | 3/4 | 中 |
| Experience Design | 2/4 | **高** |
| **总分** | **14/24** | — |

---

## 1. Copywriting（文案）— 2/4

### 问题

| 位置 | 问题 | 建议 |
|------|------|------|
| `ExplorerPage.tsx:87` | "分时图区域（IntradayChart 组件开发中）" — 开发占位文案直接出现在生产渲染路径 | 组件未就绪时应渲染骨架屏或空状态组件，而非暴露内部开发状态 |
| `StockList.tsx:68` | "暂无数据" — 空状态过于简略，用户不知道原因和下一步 | 改为："该市场暂无默认指数，点击 + 添加自定义股票" |
| `App.tsx` fallback | "加载中..." — 无意义的占位 | 使用骨架屏或至少显示加载动画 |

### 优点
- 市场名称、交易时间等标签简洁明确
- "真实数据 / 模拟数据" 区分清晰

---

## 2. Visuals（视觉）— 2/4

### 问题

| 位置 | 问题 | 建议 |
|------|------|------|
| 整体布局 | 图表区域（右侧主体）目前只是一个灰色边框占位框，占据 70%+ 宽度却没有任何视觉内容 | 即使无图表也应显示：① 空状态插画/图标 ② 操作引导 ③ 或骨架屏 |
| `StockList.tsx` 弹窗 | 添加股票弹窗使用 `position: fixed` + 半透明遮罩，但没有动画过渡，出现/消失突兀 | 添加 fadeIn/fadeOut 过渡（150-200ms） |
| 市场信息卡片 | 右侧大 icon（32px）与左侧文字信息视觉重量不平衡 | 缩小 icon 或调整布局比例 |

### 优点
- Header + 卡片 + 分段按钮 + 左右分栏的结构清晰
- 市场信息卡片的信息层次（名称 > 交易时间）合理

---

## 3. Color（色彩）— 3/4

### 问题

| 位置 | 问题 | 建议 |
|------|------|------|
| 全局 | 无暗色模式支持 | 当前不是必须的，但如果后续添加需全量改造 |
| `StockList.tsx:83` | 选中项背景色 `#eff6ff` 是硬编码的，未使用 CSS 变量 | 改为 `var(--color-primary)` 的透明变体 |

### 优点
- CSS 变量系统完善：`--color-primary`、`--color-gray-*`、`--color-bg-*`
- 色彩语义清晰：primary（蓝）= 激活/主操作，warning（橙）= 模拟模式，success（绿）= 系统状态
- 背景三层分层：深色 header → 浅灰 body → 白色卡片，深度感明确

---

## 4. Typography（排版）— 2/4

### 问题

| 位置 | 问题 | 建议 |
|------|------|------|
| 全局 | 没有 `h1`，页面直接从 `h2` 开始 | 添加语义化的 `h1`（如 "市场数据"），即使视觉上隐藏 |
| 按钮文字 | 所有分段按钮都是 `font-size-sm`（13px），在 1440px+ 屏幕上偏小 | 提升到 14px 或根据屏幕尺寸响应式调整 |
| `StockList.tsx` | 股票代码（`font-size-xs`）与名称（`font-size-sm`）的对比度不足 | 代码用更浅的颜色或更小的字号，强化名称的主导地位 |

### 优点
- 系统字体栈覆盖中西文（-apple-system, PingFang SC, Microsoft YaHei）
- 辅助信息（交易时间、股票代码）字号降级合理

---

## 5. Spacing（间距）— 3/4

### 问题

| 位置 | 问题 | 建议 |
|------|------|------|
| `ExplorerPage.tsx` | 多个元素的 `marginBottom` 硬编码为 `'var(--space-md)'` 或 `'var(--space-lg)'`，但缺少统一的 section 间距节奏 | 每个逻辑区块（市场卡、选择器、图表区）之间使用统一的 `section-gap` 变量 |
| `MarketSelector.tsx` | `gap: var(--space-sm)`（8px）对于分段按钮来说略小 | 提升到 12px |

### 优点
- CSS 变量间距系统完整：`--space-xs` 到 `--space-2xl`
- 卡片内边距统一使用 `var(--space-lg)`（16px）
- 左右分栏 `gap: var(--space-lg)` 合理

---

## 6. Experience Design（体验设计）— 2/4

### 问题

| 位置 | 问题 | 优先级 |
|------|------|--------|
| `StockList.tsx` 弹窗 | 没有 ESC 键关闭、没有点击遮罩关闭、没有焦点管理 | **高** |
| `ExplorerPage.tsx` | 切换到 K线图后没有显示任何加载或空状态，用户不知道是否已切换成功 | **高** |
| `useMarkets.ts` | 加载默认指数失败时只在 console.error，用户看不到错误 | **中** |
| 全局 | 没有任何键盘导航支持（Tab 顺序、焦点样式） | **中** |
| `useKlineData.ts` | 实时轮询每 5 秒一次，但页面不可见时仍在轮询 | **低** — 使用 `document.visibilityState` 暂停轮询 |

### 优点
- 市场切换后自动加载对应数据 — 无感切换
- 错误状态有视觉显示（ marketsError 渲染为红色文字）
- 模拟模式下才显示阶段选择器（盘前/盘中/盘后）— 条件渲染合理

---

## 架构层面的关键发现

### 合理之处
1. **useExplorer hook 的抽取** — 将 8 个 state + 3 个 callback 从页面组件中抽离，ExplorerPage 只剩纯 JSX，职责单一
2. **ErrorBoundary 的添加** — 防止子组件崩溃导致整个应用白屏
3. **CSS 工具类的引入** — `card`、`segmented-control`、`btn-segment` 消除了大量重复内联样式

### 仍需改进
1. **KlinePeriod 不应由 ExplorerPage 管理** — 周期选择（日/周/月）是 K 线图的内部状态，不应提升到页面级别。当前 ExplorerPage 同时管理 chartType 和 klinePeriod，增加了耦合。
2. **图表空状态应下沉到子组件** — ExplorerPage 直接渲染占位 `<div>` 判断 `chartType === 'kline'`，这导致页面组件了解图表内部细节。应由 `KlineChart` 和 `IntradayChart` 自己处理加载/空/错误状态。
3. **StockList 的弹窗应独立为组件** — 当前 150+ 行的 StockList 包含列表渲染 + 弹窗表单 + 状态管理，可拆分为 `StockList` + `AddStockModal`。

---

## 优先修复清单

### P0（阻塞体验）
- [ ] 移除生产代码中的开发占位文案（"组件开发中"）
- [ ] 图表区域添加骨架屏或空状态组件
- [ ] 添加股票弹窗支持 ESC / 点击遮罩关闭

### P1（显著提升）
- [ ] KlinePeriod 状态下放到 KlineChart 组件内部
- [ ] 空状态文案增加引导性（说明原因 + 操作建议）
- [ ] 页面不可见时暂停数据轮询

### P2（打磨细节）
- [ ] 弹窗添加进入/退出动画
- [ ] 键盘导航支持（Tab 顺序、焦点环）
- [ ] 分段按钮 gap 从 8px 提升到 12px

---

## 结论

当前架构在**状态分离**（useExplorer hook）和**错误防护**（ErrorBoundary）方面做得较好，但**视觉完成度**和**体验细节**还有明显差距。最大的问题是图表区域完全缺失 + 生产代码中存在开发占位文案，这两个问题应该在嵌入复杂图表之前先解决。

**建议顺序：**
1. 先修复 P0 问题（占位文案、空状态）
2. 再嵌入原始 JS 图表组件
3. 最后处理 P1/P2 体验优化
