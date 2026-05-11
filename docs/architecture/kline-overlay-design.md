# K线图动态技术指标叠加层设计

> 创建时间：2026-05-10
> 状态：待评审（v1.1 — 新增 §5 筹码面板伸缩同步 + §6 DataZoom 加载更多同步）
>
> 章节：§1 目标与约束 → §2 kline_chart.js 内部机制 → §3 方案设计 → §4 缓存与防闪烁 →
> §5 筹码面板伸缩同步 → §6 DataZoom 加载更多历史数据同步 → §7 文件变更清单 → §8 验证计划 → §9 风险与缓解

---

## 1. 设计目标与约束

### 1.1 目标

| 目标 | 说明 |
|------|------|
| G1 | 点击参数组编辑器卡片时，K 线图主区叠加该组参数计算的技术指标图形 |
| G2 | 切换参数组焦点时，瞬间切换对应指标图形（无延迟、无闪烁） |
| G3 | 拖动参数滑块修改参数值时，叠加图形实时跟随变化 |
| G4 | 同一时刻只显示当前焦点参数组的叠加图形 |
| G5 | kline_chart.js 自身不做任何修改，复用能力不受影响 |
| G6 | kline_chart.js 自带默认图形（MA5/MA10/MA20）可通过开关控制显隐 |

### 1.2 约束

| 约束 | 来源 | 影响 |
|------|------|------|
| C1 | `kline_chart.js` 不被修改，必须通过 ECharts 公开 API 操作 | overlay 系统完全外挂 |
| C2 | `render()` 使用 `setOption(option, true)` 全量替换 | 换股/切换周期后需重新挂载 overlay |
| C3 | `updateChartData()` 使用 `setOption({...}, {notMerge:false})` 按 name 合并 | 命名隔离的 overlay series 在普通数据更新中保留 |
| C4 | ECharts 实例生命周期由 kline_chart.js 管理 | overlay 系统只读不写 chartInstance 引用 |

---

## 2. kline_chart.js 内部机制（已调研）

### 2.1 Grid 结构

```
┌──────────────────────────────────┐
│  Grid 0: yAxisIndex=0 (K线主区)   │  top:6% → bottom:58%
│  ┌ K线 (candlestick)          ┐  │
│  ├ MA5  (line, #f59e0b, 0.6)  ┤  │  ← 同一 Y 轴坐标系（价格）
│  ├ MA10 (line, #6366f1, 0.6)  ┤  │
│  └ MA20 (line, #22c55e, 0.6)  ┘  │
├──────────────────────────────────┤
│  Grid 1: yAxisIndex=1 (指标区)    │  top:48% → bottom:22%
│  ┌ VOL / MACD / RSI / KDJ     ┐  │  ← 独立 Y 轴坐标系（量/比率）
│  └ OBV                        ┘  │
├──────────────────────────────────┤
│     Grid 2: 筹码分布(可选)         │
└──────────────────────────────────┘
```

### 2.2 关键渲染调用

| 函数 | 行号 | 调用 | 合并模式 | 影响 |
|------|------|------|----------|------|
| `render()` | 1572 | `setOption(option, true)` | **全量替换** | 所有外来 series 被清除 |
| `updateChartData()` | 1137 | `setOption({series:[K线,MA5,MA10,MA20]}, {notMerge:false})` | **按 name 合并** | 未匹配 series 保留 |
| `updateIndicatorData()` | 1171 | `setOption({series:[成交量/DIFF/...]}, {notMerge:false})` | **按 name 合并** | 未匹配 series 保留 |

### 2.3 render() 触发时机

`render()` 使用 `setOption(option, true)`（全量替换），所有 overlay series 被清除。

| 触发场景 | 调用链 | 用户操作 |
|---------|--------|---------|
| 首次加载数据 | `loadInitial` → `render` | 页面打开 / 换股 |
| 切换周期 | `onPeriodChange` → `loadData` → `render` | 点击日/周/月/年按钮 |
| 换股 | `setCurrent` → `init` → `loadInitial` → `render` | 输入新股票代码 |
| **切换指标** | `onIndicatorChange` → `render` | 点击 VOL/MACD/RSI/KDJ/OBV 按钮 |
| **筹码面板 resize** | 拖拽分割条 → `render` | 拖拽筹码面板宽度分割条 |

> **注意：** 除 `toggleChip()` 使用 `clear()` + `setOption(notMerge:true)` 外，上述所有场景都使用 `render()` 的 `setOption(option, true)`，且 `render()` 内部（L1580）执行 `chart.off('dataZoom')` 移除所有 dataZoom 监听器后仅重新注册筹码面板更新回调。这意味着 overlay 注册的 dataZoom 监听器也会被移除。
> 
> **`chart.off('dataZoom')` 清除范围：** 不传回调参数时移除**全局所有** dataZoom 监听器（包括 kline_chart.js 内部和外部注册的）。overlay 系统通过 `'finished'` 回调中的重注册机制（§4.4 Step A）覆盖此清除。如果未来有其他模块也注册了 dataZoom 监听器，需要同样纳入重注册机制。

### 2.4 命名空间隔离机制

```
kline_chart.js 已知 series name:
  Grid 0: 'K线', 'MA5', 'MA10', 'MA20'
  Grid 1: '成交量', 'DIFF', 'DEA', 'MACD柱', 'RSI', 'K', 'D', 'J', 'OBV'

overlay series 命名规则（不冲突）:
  Grid 0: '__overlay_{groupId}_{label}'   → 例如 '__overlay_abc123_MA(5)'
  Grid 1: '__overlay_{groupId}_{label}'   → 例如 '__overlay_abc123_DIFF'
```

---

## 3. 方案设计

### 3.1 总体架构

```
ParamGroupEditor ──onSelectGroup──→ BacktestPage (activeGroupId state)
                                         │
                                    useKlineOverlay hook
                                    ┌────────────────────┐
                                    │ cacheRef: Map       │
                                    │  groupId → {        │
                                    │    paramsHash,      │  ← 检测参数是否变化
                                    │    seriesDefs       │  ← 预计算的 series 定义
                                    │  }                  │
                                    └───────┬────────────┘
                                            │
                                    klineOverlay.ts (纯函数)
                                    ┌───────────────────────┐
                                    │ getKlineDataFromChart  │
                                    │ computeIndicator       │
                                    │ buildOverlaySeriesDef  │
                                    │ atomicSwapOverlay      │
                                    │ hideBuiltinMA          │
                                    │ restoreBuiltinMA       │
                                    └───────┬───────────────┘
                                            │
                              echarts.getInstanceByDom('mainChart')
                                            │
                                    ECharts 实例 (kline_chart.js 管理)
```

### 3.2 各策略叠加图形

| 策略 ID | 参数 | 叠加图形 | 坐标系 | 备注 |
|---------|------|---------|--------|------|
| `dual_ma` | short_period, long_period | MA(short)实线 + MA(long)虚线 | Grid 0 | 与内置 MA5/MA10/MA20 冲突 |
| `bollinger` | period, std_dev | 上轨/中轨/下轨 + 半透明填充带 | Grid 0 | 中轨即 MA(period) |
| `macd` | fast, slow, signal | DIFF线 + DEA线 + MACD柱 | Grid 1 | 与内置指标选择器下的 MACD 共存 |
| `rsi` | period | RSI线 + 70/30 参考线 | Grid 1 | 与内置指标选择器下的 RSI 共存 |

**Grid 0 策略（dual_ma, bollinger）：** 与 K 线共享价格坐标系，图形直接叠加在蜡烛图上。

**Grid 1 策略（macd, rsi）：** 与 kline_chart.js 内置指标面板共享坐标系。用户可同时查看内置 VOL 和 overlay RSI —— 前提是两者的图形不重叠（内置指标面板每次只显示一种指标，切换指标类型时旧指标被更新）。实际场景中，如果用户在 kline_chart.js 中选择了 MACD 指标，同时 overlay 也显示 MACD，会出现两套 MACD 线。这种场景由用户通过 kline_chart.js 自带的指标选择器把控（用户可将指标选择为 VOL 或其他类型以避免冲突）。

### 3.3 颜色分配

每组参数对应一个固定颜色，多线图形共享颜色不同线型：

```
Group 1 (#f59e0b amber):   MA(5)实线,  MA(20)虚线   或  Bollinger实线+填充
Group 2 (#6366f1 indigo):  MA(10)实线, MA(30)虚线   或  Bollinger实线+填充
Group 3 (#ec4899 pink):    ...
Group 4 (#14b8a6 teal):    ...
Group 5 (#f97316 orange):  ...
Group 6 (#8b5cf6 violet):  ...
```

### 3.4 kline_chart.js 默认图形开关

在 `BacktestPage` 技术回测模式下，用户通过一个 toggle 控制 kline_chart.js 自带的 MA5/MA10/MA20 是否可见。默认逻辑：

| 条件 | kline_chart.js MA 线 | overlay 图形 |
|------|---------------------|-------------|
| 无 activeGroupId（未选中任何参数组） | **显示** | 不显示 |
| 有 activeGroupId，策略为 dual_ma 或 bollinger | **隐藏** | 显示 overlay |
| 有 activeGroupId，策略为 macd 或 rsi | **显示** | 显示 overlay（Grid 1） |

隐藏方式（不修改 kline_chart.js）：
```javascript
chart.setOption({
  series: [
    { name: 'MA5',  lineStyle: { opacity: 0 }, data: [] },
    { name: 'MA10', lineStyle: { opacity: 0 }, data: [] },
    { name: 'MA20', lineStyle: { opacity: 0 }, data: [] },
  ]
});
```

恢复方式：
```javascript
chart.setOption({
  series: [
    { name: 'MA5',  lineStyle: { opacity: 0.6 } },
    { name: 'MA10', lineStyle: { opacity: 0.6 } },
    { name: 'MA20', lineStyle: { opacity: 0.6 } },
  ]
});
```

注意：`updateChartData()` 在每次 K 线数据更新时会重新设置 MA 线的 data 和 lineStyle（opacity: 0.6），因此隐藏操作在 `updateChartData()` 之后需要重新执行。由于 `updateChartData()` 在实时更新和加载更多数据时触发，overlay 系统需要在检测到 `setOption` 调用后，如果 MA 线应处于隐藏状态，则重新隐藏。实际上，更简单的做法是利用 ECharts 的 merge 特性：我们设置 `lineStyle: { opacity: 0 }` 后，`updateChartData()` 的 `setOption({series: [{name:'MA5', data:..., lineStyle:{opacity:0.6}}]})` 会用 kline_chart.js 的默认值覆盖我们的隐藏设置。因此需要用一个 `shouldHideBuiltinMA` 标志，在检测到 K 线数据更新后重新应用隐藏。

**最终方案：** 利用 §4.4 的 `'finished'` 事件统一回调，在每次渲染完成后检查 `shouldHideBuiltinMA` 状态并重新隐藏。详见 §4.4 回调中的 Step 2。

---

## 4. 缓存与防闪烁设计

### 4.1 缓存结构

```typescript
interface CachedOverlay {
  paramsHash: string;       // JSON.stringify(params) 的快照
  seriesDefs: OverlaySeriesDef[];  // ECharts series 对象数组
}

const overlayCache = useRef<Map<string, CachedOverlay>>(new Map());
```

### 4.2 三种场景的缓存行为

| 场景 | 缓存命中？ | 操作 | 用户体感 |
|------|-----------|------|---------|
| 点击参数组 B（参数未变） | ✅ | 直接从缓存取 seriesDefs → 原子替换 | **瞬时切换，零计算** |
| 点击参数组 B（参数已变） | ❌ | 重新计算 → 写入缓存 → 原子替换 | 计算耗时 < 5ms，无感知 |
| 拖动参数组 B 的滑块 | — | 重新计算 → 更新缓存 → merge 更新 | 实时跟随，无闪烁 |

**最常见场景是参数不变的切换**（用户在 3 个参数组之间对比回测结果），缓存命中率接近 100%。

### 4.3 防闪烁机制

闪烁根源：分两次 `setOption` 调用之间存在渲染间隙（先删旧 → 中间空白帧 → 再加新）。

**解决：单次 `setOption` 原子替换**

```typescript
function atomicSwapOverlay(
  chart: ECharts,
  newSeriesDefs: OverlaySeriesDef[]
): void {
  const currentSeries = chart.getOption().series as Array<{ name?: string }>;

  // 收集所有旧的 overlay series，设为空数据（仅 data:[] 足以清除视觉，
  // 不设置 lineStyle 以避免 ECharts 深合并时 opacity 残留）
  const clearOld = currentSeries
    .filter(s => typeof s.name === 'string' && s.name.startsWith('__overlay_'))
    .map(s => ({ name: s.name, data: [] }));

  // 新旧合并为一次 setOption，ECharts 原子渲染
  chart.setOption({ series: [...clearOld, ...newSeriesDefs] });
}
```

参数滑块拖动时，由于 overlay 已经显示且 series name 不变，直接 merge 更新 data 即可，ECharts 使用 `animationDurationUpdate: 300` 做平滑过渡。

### 4.4 预计算时机与 render() 后恢复

**触发预计算的场景：**
```
K 线首次加载完成 (klineLoaded: false → true)
  │
  ├─ 读取 K 线数据：chart.getOption().series.find(s => s.name === 'K线')
  ├─ 遍历所有 enabled 参数组 → 预计算指标 → 写入缓存
  └─ 如果有 activeGroupId → atomicSwapOverlay(chart, cache.get(activeGroupId))
```

**`render()` 触发后的恢复（统一机制）：**

由于 `Lifecycle.render()`（kline_chart.js L1580）执行 `chart.off('dataZoom')` 会同时删除 overlay 注册的 dataZoom 监听器，且所有 `render()` 调用场景（换股/换周期/换指标/筹码 resize）都是 `setOption(option, true)` 全量替换，overlay 必须重新注入。

**方案：监听 ECharts `'finished'` 事件**

ECharts 在每次渲染完成后触发 `'finished'` 事件，覆盖所有场景（`render()` / `toggleChip()` / `setOption` / `dispatchAction`）：

```typescript
// useKlineOverlay.ts — 注册/注销配对，合并 MA 隐藏 + overlay 注入为一次 setOption

const shouldHideBuiltinMARef = useRef(false);  // 与 state 同步，避免过期闭包
const onDataZoomRef = useRef<(() => void) | null>(null);  // 持有最新 onDataZoom 引用
const restoringRef = useRef(false);  // 防 finished 回调重入

// MA state → ref 同步（不触发额外渲染）
shouldHideBuiltinMARef.current = shouldHideBuiltinMA;

useEffect(() => {
  const chart = getChartInstance();
  if (!chart) return;

  const onFinished = () => {
    // 防重入：如果正在恢复中，跳过（ECharts 对"无变化"setOption 的行为是实现细节）
    if (restoringRef.current) return;

    const klineSeries = chart.getOption().series?.find(
      (s: any) => s.name === 'K线'
    ) as { data?: unknown[] } | undefined;

    if (!klineSeries?.data?.length) return; // K 线数据尚未就绪

    // Step A: 重新注册 dataZoom 监听器（被 render() 的 chart.off 删除了）
    const currentOnDataZoom = onDataZoomRef.current;
    if (currentOnDataZoom) {
      chart.off('dataZoom', currentOnDataZoom);
      chart.on('dataZoom', currentOnDataZoom);
    }

    // Step B: 收集所有需要注入的 series（合并为一次 setOption）
    const mergedSeries: any[] = [];

    // B1: MA 隐藏（如需要）
    if (shouldHideBuiltinMARef.current) {
      mergedSeries.push(
        { name: 'MA5',  lineStyle: { opacity: 0 }, data: [] },
        { name: 'MA10', lineStyle: { opacity: 0 }, data: [] },
        { name: 'MA20', lineStyle: { opacity: 0 }, data: [] },
      );
    }

    // B2: 清除旧 overlay（仅 data: []，不含 lineStyle 避免深合并 opacity 残留）
    // B3: 注入新 overlay（从缓存读取）
    if (activeGroupIdRef.current) {
      const currentSeries = chart.getOption().series as Array<{ name?: string }>;
      const clearOld = currentSeries
        .filter(s => typeof s.name === 'string' && s.name.startsWith('__overlay_'))
        .map(s => ({ name: s.name, data: [] }));

      const cached = overlayCache.current.get(activeGroupIdRef.current);
      if (cached) {
        mergedSeries.push(...clearOld, ...cached.seriesDefs);
      }
    }

    if (mergedSeries.length > 0) {
      restoringRef.current = true;
      chart.setOption({ series: mergedSeries });
      // setOption 是同步的（notMerge:false），渲染完成后的 'finished' 事件
      // 会被 restoringRef 守卫拦截
      restoringRef.current = false;
    }

    // Step C: 检测数据长度变化
    const xAxis0 = chart.getOption().xAxis as Array<{ data?: unknown[] }> | undefined;
    const newLength = xAxis0?.[0]?.data?.length ?? 0;
    if (newLength > 0 && newLength !== trackedKlineLengthRef.current) {
      trackedKlineLengthRef.current = newLength;
      // 长度已变化，由 dataZoom 事件在下次用户交互时触发 §6 的重算逻辑
    }
  };

  chart.on('finished', onFinished);

  return () => {
    chart.off('finished', onFinished);
  };
}, [chartReady]);
```

**`'finished'` 事件的覆盖范围：**

| 触发场景 | `'finished'` 是否触发 | overlay 恢复 |
|---------|----------------------|-------------|
| `render()`（换股/换周期/换指标/筹码resize） | ✅ 触发 | finished 回调注入 |
| `toggleChip()`（`clear()` + `setOption`） | ✅ 触发 | finished 回调注入 |
| `updateChartData()`（增量更新） | ✅ 触发 | finished 回调注入，MA 隐藏检查 |
| K 线实时更新 | ✅ 触发 | finished 回调注入，MA 隐藏检查 |

**为什么 `'finished'` 比 `requestAnimationFrame × 2` 更好：**

| 方案 | 可靠性 | 理由 |
|------|--------|------|
| `rAF × 2` | ⚠️ 不可靠 | 假设渲染在 2 帧内完成，大数据量时可能不够 |
| `'finished'` 事件 | ✅ 可靠 | ECharts 保证渲染完成后触发，不受帧率影响 |
| `getOption()` 轮询 | ⚠️ 有开销 | 需要间隔和超时控制 |

`'finished'` 事件**不产生无限循环**：回调入口有 `restoringRef` 显式守卫——第一次进入时设置 `restoringRef.current=true`，执行 `setOption` 后恢复为 `false`。`setOption` 触发的渲染完成后，`'finished'` 事件再次触发但被 `restoringRef` 拦截直接 return，循环显式终止。

> **为什么 `restoringRef` 守卫生效：** 在 `setOption` 的 **非 `lazyUpdate`** 路径（默认行为）中，ECharts 调用 `_zr.flush()` → `refreshImmediately(false)` 进行同步渲染。`refreshImmediately` 内部先调用 `animation.update(true)` 强制完成所有动画（即使 `animationDurationUpdate: 300` 已设置），再触发 `'rendered'` → `'finished'` 事件。因此 `'finished'` 在 `setOption` 返回**之前**同步触发——此时 `restoringRef.current` 仍为 `true`，守卫正确拦截。仅当使用 `lazyUpdate: true` 时，渲染和 `'finished'` 才异步触发（通过 rAF），但 overlay 系统的 `setOption` 调用均不使用此选项。

### 4.5 指标计算函数（纯函数，无副作用）

```typescript
function calcMA(data: KlineBar[], period: number): (number | string)[] {
  // 与 kline_chart.js 内部的 calcMA 逻辑一致
  return data.map((_, i) => {
    if (i < period - 1) return '-';
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += data[j].close;
    return +(sum / period).toFixed(2);
  });
}

function calcEMA(data: KlineBar[], period: number): (number | string)[] {
  const k = 2 / (period + 1);
  const result: (number | string)[] = [];
  let ema = data[0]?.close ?? 0;
  for (let i = 0; i < data.length; i++) {
    if (i === 0) { result.push('-' as const); continue; }
    ema = data[i].close * k + ema * (1 - k);
    result.push(+ema.toFixed(2));
  }
  return result;
}

function calcBollinger(
  data: KlineBar[], period: number, stdDev: number
): { upper: (number | string)[], middle: (number | string)[], lower: (number | string)[] } {
  const middle = calcMA(data, period);
  const upper: (number | string)[] = [];
  const lower: (number | string)[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) { upper.push('-'); lower.push('-'); continue; }
    const slice = data.slice(i - period + 1, i + 1).map(d => d.close);
    const mean = slice.reduce((a, b) => a + b, 0) / period;
    const variance = slice.reduce((s, v) => s + (v - mean) ** 2, 0) / period;
    const sigma = Math.sqrt(variance);
    upper.push(+(mean + stdDev * sigma).toFixed(2));
    lower.push(+(mean - stdDev * sigma).toFixed(2));
  }
  return { upper, middle, lower };
}
```

### 4.6 核心函数签名总览

`klineOverlay.ts` 纯函数模块的所有导出函数签名：

```typescript
// ===== 数据读取 =====
/** 从 ECharts 实例读取当前完整 K 线数据（含前置历史数据） */
export function getKlineDataFromChart(chart: ECharts): KlineBar[]

// ===== 指标计算 =====
/** 简单移动平均，前 period-1 个位置返回 '-' */
export function calcMA(data: KlineBar[], period: number): (number | string)[]

/** 指数移动平均，第 0 个位置返回 '-' */
export function calcEMA(data: KlineBar[], period: number): (number | string)[]

/** 布林带，返回上轨/中轨/下轨三线 */
export function calcBollinger(
  data: KlineBar[], period: number, stdDev: number
): { upper: (number | string)[]; middle: (number | string)[]; lower: (number | string)[] }

/** 计算 MACD 指标（DIFF / DEA / 柱状图） */
export function calcMACD(
  data: KlineBar[], fast: number, slow: number, signal: number
): { diff: (number | string)[]; dea: (number | string)[]; histogram: (number | string)[] }

/** 计算 RSI 指标 */
export function calcRSI(data: KlineBar[], period: number): (number | string)[]

// ===== 参数哈希 =====
/** 对参数对象做简单哈希，用于检测参数是否变化 */
export function hashParams(params: Record<string, number | boolean>): string

// ===== Series 构建 =====
/** ECharts series 定义（用于 setOption 注入） */
export interface OverlaySeriesDef {
  name: string;          // '__overlay_{groupId}_{label}'
  type: 'line' | 'bar';
  data: (number | string)[];
  xAxisIndex: 0 | 1;
  yAxisIndex: 0 | 1;
  lineStyle?: { color: string; type?: 'solid' | 'dashed'; width?: number; opacity?: number };
  itemStyle?: { color: string };
  areaStyle?: { color: string; opacity?: number };
}

/** 根据参数组 + 策略类型，构建完整的 ECharts series 定义数组 */
export function buildOverlaySeriesForGroup(
  group: ParamGroup,
  strategy: StrategyConfig,
  klineData: KlineBar[]
): OverlaySeriesDef[]

// ===== Overlay 操作 =====
/** 单次 setOption 原子替换 overlay（清除旧 + 注入新） */
export function atomicSwapOverlay(chart: ECharts, newSeriesDefs: OverlaySeriesDef[]): void

/** 隐藏 kline_chart.js 内置 MA5/MA10/MA20 */
export function hideBuiltinMA(chart: ECharts): void

/** 恢复 kline_chart.js 内置 MA5/MA10/MA20 为默认显示 */
export function restoreBuiltinMA(chart: ECharts): void

// ===== 数据同步 =====
/** 检测 K 线 xAxis 数据长度变化。返回新长度或 null */
export function detectKlineLengthChange(chart: ECharts, lastLength: number): number | null

/** 全量重建所有已启用的参数组 overlay 缓存 */
export function rebuildAllCachedOverlays(
  chart: ECharts,
  paramGroups: ParamGroup[],
  strategy: StrategyConfig
): Map<string, CachedOverlay>
```

---

## 5. 筹码分布面板伸缩同步

### 5.1 问题分析

筹码分布面板（Grid 2）的显示/隐藏由 `window.KlineChart.toggleChipPanel()` 触发，实际执行路径为：

```
window.KlineChart.toggleChipPanel()
  → Interaction.toggleChip()
    → State.ui.chipVisible = !State.ui.chipVisible
    → ChartBuilder.buildOption()            // 重新构建完整 option
    → State.chartInstance.clear()           // ⚠️ 销毁所有组件（series/grid/axes 全部清除）
    → State.chartInstance.setOption(option, { notMerge: true, lazyUpdate: false })
```

**关键发现：`toggleChip()` 比 `render()` 更具破坏性。**

| 操作 | 方法 | 影响 |
|------|------|------|
| `render()` | `setOption(option, true)` | 全量替换，所有 overlay series 被清除 |
| `toggleChip()` | `clear()` + `setOption(option, {notMerge:true})` | **清空图表引擎** → 全量重建，连 grid/axes 都被销毁再创建 |

这意味着筹码面板切换后，overlay 系统处于**完全空白**状态 —— 不仅 series 没了，连 grid 引用都已重建。

### 5.2 Grid 布局变化

筹码面板显隐改变了 Grid 0/1 的右边界：

```
筹码隐藏 (chipVisible = false):
  Grid 0: left:40, right:40,  top:6%,  bottom:58%
  Grid 1: left:40, right:40,  top:48%, bottom:22%

筹码显示 (chipVisible = true):
  Grid 0: left:40, right:chipWidth+20, top:6%,  bottom:58%
  Grid 1: left:40, right:chipWidth+20, top:48%, bottom:22%
  Grid 2: right:10, width:chipWidth,   top:6%,  bottom:58%   ← 新增
```

overlay series 通过 `xAxisIndex: 0/1` 和 `yAxisIndex: 0/1` 绑定到对应 grid。Grid 0/1 的索引始终不变（筹码面板是 Grid 2），因此 overlay series 的 `xAxisIndex` / `yAxisIndex` **无需修改**。但整个 option 已被 `clear()` + 重建，overlay series 必须**重新注入**。

### 5.3 设计方案：公开 API 包装器（Monkey-Patch）

**核心思路：** 不修改 `kline_chart.js` 文件本身，而是在运行时包装 `window.KlineChart.toggleChipPanel`，在原始调用前后插入 overlay 的销毁与恢复逻辑。

```
包装后的 toggleChipPanel():
  1. 记录当前 activeGroupId（overlay 状态快照）
  2. 调用原始 toggleChipPanel()
     → Interaction.toggleChip()
     → chart.clear() + setOption(notMerge:true)   [overlay 全部被摧毁]
  3. requestAnimationFrame × 2（等 ECharts 完成渲染）
  4. 从缓存取出 seriesDefs → atomicSwap 重新注入 overlay
     （MA 隐藏由 'finished' 事件回调 §4.4 统一处理，此处仅恢复 overlay）
```

**为什么选择 Monkey-Patch 而非事件监听？**

| 方案 | 可行性 | 理由 |
|------|--------|------|
| ECharts `resize` 事件 | ❌ | `clear()` 后组件被销毁，resize 事件不触发 |
| 轮询检测 grid 变化 | ❌ | `clear()` 后 `getOption().grid` 为 `[]`，无法区分"刚清除"与"尚未重建" |
| DOM MutationObserver | ⚠️ 部分可行 | 可检测 K 线容器尺寸变化，但无法区分筹码切换与其他 resize |
| **Monkey-Patch 公开 API** | ✅ | 精确知道切换发生的时刻，零误判 |

> **Monkey-Patch 与 `'finished'` 事件的关系：** `toggleChip()` 完成后，`'finished'` 事件（§4.4）和 Monkey-Patch 的 rAF 回调会先后触发 overlay 恢复。两条路径的操作都是幂等的（相同缓存 → 相同 `setOption`），`'finished'` 回调有 `restoringRef` 守卫防止重入。Monkey-Patch 的 `togglePendingRef` 守卫用于防止快速连续点击的 rAF 堆积。保留两条路径的理由：rAF 路径在 `'finished'` 因未知原因未触发时提供同步回退，且 `togglePendingRef` 可在 ECharts 渲染完成前即阻止连续点击的堆积（`'finished'` 是异步事件，无法提前阻止）。

### 5.4 Monkey-Patch 实现要点

```typescript
// useKlineOverlay.ts 中
const originalToggleChip = useRef<(() => void) | null>(null);
const togglePendingRef = useRef(false);  // 防快速点击守卫
const toggleRafIdRef = useRef<number | null>(null);  // 用于取消排期的 rAF

// 挂载时安装包装器
useEffect(() => {
  if (!window.KlineChart?.toggleChipPanel) return;

  originalToggleChip.current = window.KlineChart.toggleChipPanel;

  window.KlineChart.toggleChipPanel = () => {
    // 防快速连续点击：如果上一次恢复尚未完成，跳过本次排队
    if (togglePendingRef.current) {
      // 仍然执行原始切换（用户期望的行为），但不追加新的恢复逻辑
      originalToggleChip.current!();
      return;
    }

    originalToggleChip.current!();  // 原始切换（会清除 overlay）
    togglePendingRef.current = true;

    // 等 ECharts 重建完成（使用 'finished' 事件更可靠，此处为 Monkey-Patch 的同步回退）
    toggleRafIdRef.current = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        toggleRafIdRef.current = null;
        togglePendingRef.current = false;
        const chart = echarts.getInstanceByDom(document.getElementById('mainChart'));
        if (!chart) return;

        // overlay 恢复（此时 'finished' 事件也会做同样的事——幂等操作）
        if (activeGroupIdRef.current) {
          const cached = overlayCache.current.get(activeGroupIdRef.current);
          if (cached) {
            atomicSwapOverlay(chart, cached.seriesDefs);
          }
        }
      });
    });
  };

  // 卸载时恢复原始函数 + 取消排期的 rAF + 复位守卫
  return () => {
    if (toggleRafIdRef.current !== null) {
      cancelAnimationFrame(toggleRafIdRef.current);
      toggleRafIdRef.current = null;
    }
    togglePendingRef.current = false;  // StrictMode remount 时复位
    if (originalToggleChip.current) {
      window.KlineChart.toggleChipPanel = originalToggleChip.current;
    }
  };
}, []);  // 依赖为空，Monkey-Patch 仅安装一次

**安全性保证：**
1. `togglePendingRef` 防止快速连续点击导致的 rAF 回调堆积
2. 防抖期间仍执行原始切换（用户期望的行为），仅跳过重复的 overlay 恢复
3. 组件卸载时恢复原始 `toggleChipPanel` 引用
4. 包装逻辑仅在有 activeGroupId 时才注入 overlay（无副作用）
5. 不影响 kline_chart.js 在其他页面的独立使用

### 5.5 同步正确性验证矩阵

| 场景 | 筹码切换前 | 筹码切换后 | 预期 |
|------|-----------|-----------|------|
| 无 activeGroupId | K 线正常显示 | K 线正常（Grid 伸缩） | overlay 不注入 |
| 有 activeGroupId + dual_ma | 显示 overlay MA 线 | Grid 伸缩 + overlay MA 线恢复 | 注入 overlay |
| 有 activeGroupId + bollinger | 显示布林带 | Grid 伸缩 + 布林带恢复 | 注入 overlay |
| 有 activeGroupId + macd/rsi | 显示 Grid 1 overlay | Grid 伸缩 + overlay 恢复 | 注入 overlay |

---

## 6. DataZoom 与加载更多历史数据同步

### 6.1 问题分析

kline_chart.js 的无限滚动机制通过 `DataService.startInfiniteScroll()`（每 100ms 轮询）检测 dataZoom 位置，当用户向左滚动超过阈值时触发 `DataService.loadHistory()`。数据加载流程：

```
DataService.loadHistory()
  → fetch 历史数据 API
  → uniqueNewData.concat(State.data.kline)    // ⚠️ 数据前置插入
  → DataService.updateChartData()            // 更新 K线 + MA5/10/20
  → DataService.adjustZoomAfterPrepend()     // 调整 dataZoom 位置
```

**`updateChartData()` 的关键行为（L1137-L1156）：**

```javascript
State.chartInstance.setOption({
  xAxis: [
    { data: dates },    // ← 新的完整日期数组（包含前置数据）
    { data: dates }
  ],
  series: [
    { name: 'K线', data: ohlc },
    { name: 'MA5', data: calcMA(State.data.kline, 5) },
    { name: 'MA10', data: calcMA(State.data.kline, 10) },
    { name: 'MA20', data: calcMA(State.data.kline, 20) }
  ]
}, { notMerge: false, lazyUpdate: true })
```

**使用 `notMerge: false`，这意味着名称未知的 series（包括所有 `__overlay_*`）会被保留。** 这是好消息 —— overlay series 不会在数据加载时被删除。

**但是，存在数据长度不一致问题：**

```
加载前: K 线 200 条 → overlay data 数组长度 200 → 索引对齐 ✅
加载后: K 线 250 条 → overlay data 数组长度 200 → 索引错位 ❌
```

由于历史数据是**前置插入**（prepend），原有的 overlay data[0] 对应的是加载前的第 1 根 K 线，加载后它仍然占据索引 0，但此时索引 0 已经是一根新的、更早的 K 线。**overlay 图形整体向右偏移了 50 个位置。**

`adjustZoomAfterPrepend()` 通过调整 dataZoom 的 start/end 百分比来保持用户视图不跳跃，但这只是视觉层面 —— **底层数据数组的索引对齐问题没有解决**。

### 6.2 解决方案：K 线数据长度变更检测 + 全量重算

**核心策略：** 监听 ECharts 的 dataZoom 事件，在每次事件触发时检测 xAxis[0].data 的长度是否发生变化。如果变化，说明历史数据已加载，需要重新计算所有已缓存的 overlay 指标。

```
dataZoom 事件触发
  │
  ├─ 读取 currentKlineLength = chart.getOption().xAxis[0].data.length
  ├─ 比较 trackedKlineLength（上次记录的值）
  │
  ├─ currentKlineLength === trackedKlineLength → 无需操作（正常滚动）
  │
  └─ currentKlineLength !== trackedKlineLength → 检测到数据变更！
       │
       ├─ 更新 trackedKlineLength = currentKlineLength
       ├─ 从 ECharts 读取完整 K 线数据（chart.getOption().series[0].data）
       ├─ 遍历 overlayCache 中所有条目 → 重新计算指标 → 更新 seriesDefs
       └─ 如果有 activeGroupId → atomicSwapOverlay 更新当前显示
```

### 6.3 为什么选择 dataZoom 事件？

| 检测方式 | 可用性 | 理由 |
|---------|--------|------|
| **dataZoom 事件** | ✅ 推荐 | loadHistory 后 `adjustZoomAfterPrepend` 会触发 dataZoom；用户正常滚动也触发 dataZoom，但通过长度检测过滤掉无变更的情况 |
| 轮询 `xAxis[0].data.length` | ⚠️ 备选 | 100ms 间隔轮询可行但浪费资源 |
| MutationObserver | ❌ | canvas 渲染不产生 DOM 变更 |

### 6.4 重算优化：避免每次 dataZoom 都全量重算

```
方案 A（当前推荐）：长度检测 + 全量重算
  - 仅在 dataZoom 事件中检测到长度变更时才重算
  - 一次加载更多数据 → 只触发一次重算
  - 正常滚动（长度未变）→ 零开销

方案 B（更激进）：防抖重算
  - 如果用户快速连续加载多批数据，对重算做 300ms 防抖
  - 当前代码中 loadHistory 有 isLoadingMore 互斥锁，连续加载场景不常见
  - 暂不采用，可在实际使用中发现需要时再添加
```

### 6.5 完整的 dataZoom 处理逻辑

```typescript
// klineOverlay.ts 纯函数

/**
 * 检测 K 线数据长度是否变更。
 * 返回新长度如果变更，否则返回 null。
 */
export function detectKlineLengthChange(chart: ECharts, lastLength: number): number | null {
  const option = chart.getOption();
  const xAxis0 = option.xAxis as Array<{ data?: unknown[] }> | undefined;
  if (!xAxis0?.[0]?.data) return null;
  const currentLength = xAxis0[0].data.length;
  return currentLength !== lastLength ? currentLength : null;
}

/**
 * 从 ECharts 实例读取完整 K 线数据，重建所有缓存 overlay。
 * 返回更新后的 cache Map。
 */
export function rebuildAllCachedOverlays(
  chart: ECharts,
  paramGroups: ParamGroup[],
  strategy: StrategyConfig
): Map<string, CachedOverlay> {
  const klineData = getKlineDataFromChart(chart);
  const newCache = new Map<string, CachedOverlay>();

  for (const group of paramGroups) {
    if (!group.enabled) continue;
    const seriesDefs = buildOverlaySeriesForGroup(group, strategy, klineData);
    newCache.set(group.id, {
      paramsHash: hashParams(group.params),
      seriesDefs,
    });
  }

  return newCache;
}
```

```typescript
// useKlineOverlay.ts hook 中

const trackedKlineLengthRef = useRef(0);
const onDataZoomRef = useRef<(() => void) | null>(null);  // 供 §4.4 onFinished 通过 ref 访问

// 注册 dataZoom 事件监听
useEffect(() => {
  const chart = getChartInstance();
  if (!chart) return;

  const onDataZoom = () => {
    const newLength = detectKlineLengthChange(chart, trackedKlineLengthRef.current);
    if (newLength === null) return; // 长度未变，忽略

    trackedKlineLengthRef.current = newLength;

    // 全量重算缓存
    const newCache = rebuildAllCachedOverlays(
      chart,
      paramGroups,
      strategy
    );
    overlayCache.current = newCache;

    // 重新应用当前 overlay
    if (activeGroupIdRef.current) {
      const cached = newCache.get(activeGroupIdRef.current);
      if (cached) {
        atomicSwapOverlay(chart, cached.seriesDefs);
      }
    }
  };

  onDataZoomRef.current = onDataZoom;  // 同步最新引用到 ref
  chart.on('dataZoom', onDataZoom);
  return () => { chart.off('dataZoom', onDataZoom); };
}, [chartReady, paramGroups, strategy]);
```

**注意：** `adjustZoomAfterPrepend()` 通过 `dispatchAction({ type: 'dataZoom' })` 调整 dataZoom 位置，这会触发 dataZoom 事件。但此时 `xAxis[0].data.length` 已经在 `updateChartData()` 中更新为新长度，因此 `detectKlineLengthChange` 会检测到变更并触发重算 —— 这正是我们期望的行为。重算仅在一次加载完成后执行一次（`isLoadingMore` 互斥锁保证），后续正常的 dataZoom 滚动事件因长度未变而被跳过。

> **关于 kline_chart.js 中的 `window.__dataZoomAdjusting`:** 该变量在 `adjustZoomAfterPrepend()`（L1248-L1262）中以 setter 模式调用 `window.__dataZoomAdjusting(true/false)`，但由于从未在任何地方定义此函数，这些调用是静默无操作。overlay 系统不使用此标志 —— 仅依赖长度检测，更简洁可靠。

### 6.6 同步正确性验证矩阵

| 场景 | 数据变化 | overlay 行为 | 预期 |
|------|---------|-------------|------|
| 首次加载 K 线 | K 线 200 条 | overlay 预计算 200 条数据并缓存 | ✅ |
| 用户向左滚动触发加载 | +50 条前置数据 | dataZoom 事件 → 检测长度变化 → 全量重算 250 条 → 更新 overlay | ✅ |
| 用户正常滚动（无加载） | 长度不变 | dataZoom 事件 → 长度检测 → null → 跳过 | ✅ |
| 用户切换筹码面板 | clear + 重建 | Monkey-Patch 触发 overlay 恢复（§5 已覆盖） | ✅ |
| 快速连续加载两批数据 | +50 +50 | 第 1 批重算 → 第 2 批重算（isLoadingMore 互斥保证不并发） | ✅ |
| 实时 K 线更新（交易时段） | 最后一根 K 线更新 | updateChartData() notMerge:false 保留 overlay；数据长度不变 → 跳过重算 | ✅ |

---

## 7. 文件变更清单

### 7.1 新建文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `apps/dsa-web/src/utils/klineOverlay.ts` | ~300 | 纯函数：指标计算、series 构建、原子替换、MA 显隐、K线数据长度变更检测、全量缓存重建 |
| `apps/dsa-web/src/hooks/useKlineOverlay.ts` | ~160 | React hook：缓存管理、生命周期、activeGroupId 监听、toggleChipPanel Monkey-Patch、dataZoom 事件监听 |

### 7.2 修改文件

| 文件 | 变更量 | 说明 |
|------|--------|------|
| `apps/dsa-web/src/components/backtest/ParamGroupEditor.tsx` | +12行 | 新增 `activeGroupId` / `onSelectGroup` props |
| `apps/dsa-web/src/pages/BacktestPage.tsx` | +50行 | 新增 `activeGroupId` state + `builtinMAVisible` toggle state，引入 useKlineOverlay，传入 ParamGroupEditor，添加 MA 显示开关 UI |
| `apps/dsa-web/src/types/technicalBacktest.ts` | +10行 | 新增 `OverlaySeriesDef`、`CachedOverlay`、`KlineBar` 接口定义 |
| `apps/dsa-web/src/hooks/useTechnicalBacktest.ts` | +3行 | 暴露 `activeGroupId` 状态（或直接在 BacktestPage 中管理） |

### 7.3 不修改文件

```
public/js/kline_chart.js           ← 完全不动
api/v1/endpoints/chart.py          ← 完全不动
```

---

## 8. 验证计划

### 8.1 功能验证

| 验证项 | 步骤 | 预期 |
|--------|------|------|
| 叠加显示 | 加载 K 线 → 选择 dual_ma 策略 → 点击参数组 1 | K 线图上出现该组参数的 MA 线 |
| 焦点切换 | 点击参数组 2（不同参数） | 图形瞬间切换为参数组 2 的 MA 线 |
| 参数拖动 | 拖动参数组 1 的滑块 | 叠加图形实时跟随变化 |
| MA 冲突隐藏 | 激活 dual_ma 参数组 | kline_chart.js 内置 MA5/MA10/MA20 隐藏 |
| MA 恢复 | 取消所有参数组选中（activeGroupId = null） | 内置 MA5/MA10/MA20 恢复显示 |
| 换股后恢复 | 激活参数组 → 换股 → K 线加载完成 | overlay 重新挂载（缓存或重算） |
| 缓存验证 | 切换到参数组 1 → 切到参数组 2 → 切回参数组 1 | 第二次切换瞬间显示，无计算延迟 |

### 8.2 筹码面板伸缩同步验证

| 验证项 | 步骤 | 预期 |
|--------|------|------|
| 筹码展开时 overlay 保持 | 激活 overlay → 点击筹码分布按钮展开 | K 线图 Grid 伸缩，overlay 图形保持显示不倒挂 |
| 筹码收起时 overlay 保持 | 筹码已展开 + overlay 激活 → 点击筹码按钮收起 | Grid 恢复，overlay 图形保持显示 |
| 无 overlay 时筹码切换 | 未选中任何参数组 → 切换筹码面板 | K 线正常伸缩，无异常 |
| 筹码切换后焦点不变 | overlay 显示参数组 1 → 切换筹码 → 操作参数组 2 | 参数组 2 的 overlay 正确显示 |

### 8.3 DataZoom 加载更多同步验证

| 验证项 | 步骤 | 预期 |
|--------|------|------|
| 加载历史后 overlay 对齐 | overlay 激活 → 向左滚动触发加载更多 → 等待数据加载完成 | overlay 指标与新 K 线数据正确对齐 |
| 正常滚动不受影响 | overlay 激活 → 左右滚动（不触发加载） | 无重算，overlay 图形跟随滚动正常 |
| 多次加载叠加 | 连续向左滚动触发 2-3 次加载 | 每次加载后 overlay 数据长度匹配 K 线 |
| 实时更新时 overlay 保持 | 交易时段 overlay 激活 → K 线实时更新 | overlay 不被清除，数据长度不变跳过重算 |
| 筹码展开 + 加载更多 | 筹码面板展开状态 → overlay 激活 → 向左滚动触发加载历史数据 | overlay 在 Grid 伸缩状态下正确对齐新数据 |
| 筹码展开 + 换股 | 筹码面板展开状态 → overlay 激活 → 输入新股票代码 | overlay 在新股票 K 线加载完成后正确恢复 |
| 筹码展开 → 收拢 → 加载更多 | overlay 激活 → 展开筹码 → 收拢筹码 → 加载历史 | overlay 在最终 Grid 状态下数据对齐正确 |

### 8.4 构建验证

```bash
cd apps/dsa-web && npm run lint && npm run build
```

### 8.5 回归验证

- kline_chart.js 在其他页面（如 AI 回测页）的行为不受影响
- 后端 112 个测试全部通过

---

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| `updateChartData()` 恢复 MA 线 opacity | `requestAnimationFrame` 延迟重新隐藏 |
| `render()` 清除 overlay | 轮询检测 K 线数据就绪后重新挂载 |
| `toggleChip()` 的 `clear()` 摧毁 overlay | Monkey-Patch `window.KlineChart.toggleChipPanel`，在原始调用后 `requestAnimationFrame` × 2 恢复 overlay |
| 加载历史数据后 overlay 数据长度不匹配 | dataZoom 事件中检测 `xAxis[0].data.length` 变化，触发全量重算 + 缓存更新 |
| 快速连续加载多批数据导致重复重算 | `isLoadingMore` 互斥锁保证不并发；长度检测跳过相同长度的后续触发 |
| 实时 K 线更新时 overlay 数据长度不匹配 | overlay 使用与 K 线同步的数据源（chart.getOption()）；长度未变 → 跳过重算 |
| 策略切换时缓存失效 | 监听 `selectedStrategyId` 变化，清空缓存 |
| Monkey-Patch 未及时恢复造成内存泄漏 | `useEffect` cleanup 中恢复原始 `toggleChipPanel` 引用 |
| `buildOption()` 中 dataZoom start/end 使用旧值导致重算后 zoom 跳动 | 使用 ECharts `getOption().dataZoom` 读取当前实际值，不依赖缓存的百分比 |
| 快速连续点击筹码按钮导致 Monkey-Patch 回调堆积 | `togglePendingRef` 守卫：如果上次恢复尚未完成，仅执行原始切换，不追加新的恢复逻辑 |
| React StrictMode 下 useEffect 双重挂载/卸载导致 Monkey-Patch 污染 | cleanup 中恢复原始引用；挂载前检查 `originalToggleChip.current` 是否已保存，避免嵌套包装 |
| ECharts `'finished'` 事件在极大数据量时延迟超过 33ms | overlay re-injection 是幂等操作，延迟仅影响用户体验（短暂的 overlay 缺失），不影响数据完整性 |

---

> 本文档完成后，待确认后方可开始实施。
