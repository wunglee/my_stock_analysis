/**
 * K线图技术指标叠加层 — 纯函数模块
 *
 * 不修改 kline_chart.js，完全通过 ECharts 公开 API 操作。
 * 所有函数无副作用（除 atomicSwapOverlay / hideBuiltinMA / restoreBuiltinMA 通过 setOption 操作图表）。
 */

import type { ParamGroup, StrategyConfig, KlineData } from '../types/technicalBacktest';

// KlineBar 与 KlineData 字段相同，语义上强调从 ECharts 读取的 K 线数据
export type KlineBar = KlineData;

// ============ 类型定义 ============

export interface OverlaySeriesDef {
  name: string;
  type: 'line' | 'bar';
  data: (number | string)[];
  xAxisIndex: 0 | 1;
  yAxisIndex: 0 | 1;
  animation: false;
  lineStyle?: { color: string; type?: 'solid' | 'dashed'; width?: number; opacity?: number };
  itemStyle?: { color: string };
  areaStyle?: { color: string; opacity?: number };
}

export interface CachedOverlay {
  paramsHash: string;
  seriesDefs: OverlaySeriesDef[];
}

// 颜色池：每组参数对应一个固定颜色
const GROUP_COLORS = [
  '#f59e0b', // amber
  '#6366f1', // indigo
  '#ec4899', // pink
  '#14b8a6', // teal
  '#f97316', // orange
  '#8b5cf6', // violet
];

// ============ 数据读取 ============

/** 从 ECharts 实例读取当前完整 K 线数据 */
export function getKlineDataFromChart(chart: any): KlineBar[] {
  const option = chart.getOption();
  if (!option || !option.series) return [];
  const series = option.series as Array<{ name?: string; data?: unknown[] }>;
  const klineSeries = series.find((s) => s.name === 'K线');
  if (!klineSeries?.data) return [];

  const rawData = klineSeries.data;
  if (rawData.length === 0) return [];

  // 数据已是 KlineBar 对象 → 直接返回
  if (typeof rawData[0] === 'object' && !Array.isArray(rawData[0])) {
    return rawData as KlineBar[];
  }

  // ECharts candlestick 数组格式 [open, close, low, high] → 转换为 KlineBar 对象
  const xAxisData = (option.xAxis as Array<{ data?: string[] }>)?.[0]?.data ?? [];
  return (rawData as number[][]).map((item, i) => ({
    date: xAxisData[i] ?? '',
    open: item[0] ?? 0,
    close: item[1] ?? 0,
    low: item[2] ?? 0,
    high: item[3] ?? 0,
    volume: 0,
  }));
}

// ============ 指标计算 ============

export function calcMA(data: KlineBar[], period: number): (number | string)[] {
  return data.map((_, i) => {
    if (i < period - 1) return '-';
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += data[j].close;
    return +(sum / period).toFixed(2);
  });
}

export function calcEMA(data: KlineBar[], period: number): (number | string)[] {
  const k = 2 / (period + 1);
  const result: (number | string)[] = [];
  let ema = data[0]?.close ?? 0;
  for (let i = 0; i < data.length; i++) {
    if (i === 0) { result.push('-'); continue; }
    ema = data[i].close * k + ema * (1 - k);
    result.push(+ema.toFixed(2));
  }
  return result;
}

export function calcBollinger(
  data: KlineBar[],
  period: number,
  stdDev: number,
): { upper: (number | string)[]; middle: (number | string)[]; lower: (number | string)[] } {
  const middle = calcMA(data, period);
  const upper: (number | string)[] = [];
  const lower: (number | string)[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) { upper.push('-'); lower.push('-'); continue; }
    const slice = data.slice(i - period + 1, i + 1).map((d) => d.close);
    const mean = slice.reduce((a, b) => a + b, 0) / period;
    const variance = slice.reduce((s, v) => s + (v - mean) ** 2, 0) / period;
    const sigma = Math.sqrt(variance);
    upper.push(+(mean + stdDev * sigma).toFixed(2));
    lower.push(+(mean - stdDev * sigma).toFixed(2));
  }
  return { upper, middle, lower };
}

export function calcMACD(
  data: KlineBar[],
  fast: number,
  slow: number,
  signal: number,
): { diff: (number | string)[]; dea: (number | string)[]; histogram: (number | string)[] } {
  const emaFast = calcEMA(data, fast) as number[];
  const emaSlow = calcEMA(data, slow) as number[];
  const diff: (number | string)[] = [];
  const dea: (number | string)[] = [];
  const histogram: (number | string)[] = [];

  for (let i = 0; i < data.length; i++) {
    const d = typeof emaFast[i] === 'number' && typeof emaSlow[i] === 'number'
      ? +(emaFast[i] - emaSlow[i]).toFixed(2)
      : '-';
    diff.push(d);
  }

  // DEA = EMA of DIFF
  const deaK = 2 / (signal + 1);
  let deaValue = 0;
  let firstDiff = false;
  for (let i = 0; i < diff.length; i++) {
    if (typeof diff[i] !== 'number') { dea.push('-'); continue; }
    if (!firstDiff) {
      deaValue = diff[i] as number;
      firstDiff = true;
      dea.push(+deaValue.toFixed(2));
      continue;
    }
    deaValue = (diff[i] as number) * deaK + deaValue * (1 - deaK);
    dea.push(+deaValue.toFixed(2));
  }

  for (let i = 0; i < data.length; i++) {
    if (typeof diff[i] !== 'number' || typeof dea[i] !== 'number') {
      histogram.push('-');
    } else {
      histogram.push(+((diff[i] as number) - (dea[i] as number)).toFixed(2));
    }
  }

  return { diff, dea, histogram };
}

export function calcRSI(data: KlineBar[], period: number): (number | string)[] {
  const result: (number | string)[] = [];
  let avgGain = 0;
  let avgLoss = 0;

  for (let i = 0; i < data.length; i++) {
    if (i === 0) { result.push('-'); continue; }
    const change = data[i].close - data[i - 1].close;
    const gain = Math.max(change, 0);
    const loss = Math.max(-change, 0);

    if (i < period) {
      avgGain += gain;
      avgLoss += loss;
      if (i === period - 1) {
        avgGain /= period;
        avgLoss /= period;
        const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
        result.push(+(100 - 100 / (1 + rs)).toFixed(2));
      } else {
        result.push('-');
      }
    } else {
      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;
      const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
      result.push(+(100 - 100 / (1 + rs)).toFixed(2));
    }
  }

  return result;
}

// ============ 参数哈希 ============

export function hashParams(params: Record<string, number | boolean>): string {
  const sorted = Object.keys(params).sort().map((k) => `${k}:${params[k]}`);
  return sorted.join('|');
}

// ============ Series 构建 ============

function getColor(index: number): string {
  return GROUP_COLORS[index % GROUP_COLORS.length];
}

export function buildOverlaySeriesForGroup(
  group: ParamGroup,
  strategy: StrategyConfig,
  klineData: KlineBar[],
  colorIndex: number,
): OverlaySeriesDef[] {
  const color = getColor(colorIndex);
  const groupId = group.id;
  const prefix = `__overlay_${groupId}`;

  switch (strategy.id) {
    case 'dual_ma': {
      const short = group.params.short_period as number;
      const long = group.params.long_period as number;
      const maShort = calcMA(klineData, short);
      const maLong = calcMA(klineData, long);
      return [
        {
          name: `${prefix}_MA(${short})`,
          type: 'line',
          data: maShort,
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          lineStyle: { color, type: 'solid', width: 1.5 },
        },
        {
          name: `${prefix}_MA(${long})`,
          type: 'line',
          data: maLong,
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          lineStyle: { color, type: 'dashed', width: 1.5 },
        },
      ];
    }

    case 'bollinger': {
      const period = group.params.period as number;
      const stdDev = group.params.std_dev as number;
      const { upper, middle, lower } = calcBollinger(klineData, period, stdDev);
      return [
        {
          name: `${prefix}_Upper(${period},${stdDev})`,
          type: 'line',
          data: upper,
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          lineStyle: { color, type: 'solid', width: 1 },
        },
        {
          name: `${prefix}_Middle(${period})`,
          type: 'line',
          data: middle,
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          lineStyle: { color, type: 'dashed', width: 1 },
        },
        {
          name: `${prefix}_Lower(${period},${stdDev})`,
          type: 'line',
          data: lower,
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          lineStyle: { color, type: 'solid', width: 1 },
          areaStyle: { color, opacity: 0.08 },
        },
      ];
    }

    case 'macd': {
      const fast = group.params.fast as number;
      const slow = group.params.slow as number;
      const signal = group.params.signal as number;
      const { diff, dea, histogram } = calcMACD(klineData, fast, slow, signal);
      return [
        {
          name: `${prefix}_DIFF(${fast},${slow})`,
          type: 'line',
          data: diff,
          xAxisIndex: 1,
          yAxisIndex: 1,
          animation: false,
          lineStyle: { color, type: 'solid', width: 1 },
        },
        {
          name: `${prefix}_DEA(${fast},${slow},${signal})`,
          type: 'line',
          data: dea,
          xAxisIndex: 1,
          yAxisIndex: 1,
          animation: false,
          lineStyle: { color: '#f97316', type: 'solid', width: 1 },
        },
        {
          name: `${prefix}_MACD柱(${fast},${slow},${signal})`,
          type: 'bar',
          data: histogram,
          xAxisIndex: 1,
          yAxisIndex: 1,
          animation: false,
          itemStyle: { color },
        },
      ];
    }

    case 'rsi': {
      const period = group.params.period as number;
      const rsi = calcRSI(klineData, period);
      const ref70 = new Array(klineData.length).fill(70);
      const ref30 = new Array(klineData.length).fill(30);
      return [
        {
          name: `${prefix}_RSI(${period})`,
          type: 'line',
          data: rsi,
          xAxisIndex: 1,
          yAxisIndex: 1,
          animation: false,
          lineStyle: { color, type: 'solid', width: 1.5 },
        },
        {
          name: `${prefix}_RSI_70`,
          type: 'line',
          data: ref70,
          xAxisIndex: 1,
          yAxisIndex: 1,
          animation: false,
          lineStyle: { color: '#ef4444', type: 'dashed', width: 0.5, opacity: 0.5 },
        },
        {
          name: `${prefix}_RSI_30`,
          type: 'line',
          data: ref30,
          xAxisIndex: 1,
          yAxisIndex: 1,
          animation: false,
          lineStyle: { color: '#22c55e', type: 'dashed', width: 0.5, opacity: 0.5 },
        },
      ];
    }

    default:
      return [];
  }
}

// ============ Overlay 操作 ============

export function atomicSwapOverlay(chart: any, newSeriesDefs: OverlaySeriesDef[]): void {
  if (newSeriesDefs.length === 0) return;

  const currentSeries = chart.getOption().series as Array<{ name?: string; data?: unknown[] }>;
  const xAxisOption = chart.getOption().xAxis as Array<{ data?: unknown[] }>;
  const xAxisLen = xAxisOption?.[0]?.data?.length ?? 0;

  // 幂等守卫：所有 overlay 已存在且数据长度与 xAxis 对齐 → 跳过
  if (xAxisLen > 0) {
    const allAligned = newSeriesDefs.every((def) => {
      const existing = currentSeries.find((s) => s.name === def.name);
      return existing != null && (existing.data?.length ?? 0) === xAxisLen;
    });
    if (allAligned) return;
  }

  // 防止应用过期缓存：dataZoom 加载更多数据后，缓存的 overlay 长度可能与
  // 当前 xAxis 不匹配。此时跳过，让 onDataZoom 处理器用新鲜数据重建。
  if (xAxisLen > 0 && newSeriesDefs[0].data.length !== xAxisLen) return;

  // 保留非 overlay series（K线、MA、成交量等），丢弃旧的 __overlay_ series
  const nonOverlay = currentSeries.filter(
    (s) => !(typeof s.name === 'string' && s.name.startsWith('__overlay_')),
  );

  chart.setOption({ series: [...nonOverlay, ...newSeriesDefs] }, { replaceMerge: ['series'] });
}

export function hideBuiltinMA(chart: any): void {
  chart.setOption({
    series: [
      { name: 'MA5', lineStyle: { opacity: 0 } },
      { name: 'MA10', lineStyle: { opacity: 0 } },
      { name: 'MA20', lineStyle: { opacity: 0 } },
    ],
  });
}

/** 移除所有 __overlay_ 前缀的 series（焦点离开参数组时调用） */
export function clearOverlays(chart: any): void {
  const currentSeries = chart.getOption().series as Array<{ name?: string }>;
  const nonOverlay = currentSeries.filter(
    (s) => !(typeof s.name === 'string' && s.name.startsWith('__overlay_')),
  );
  chart.setOption({ series: nonOverlay }, { replaceMerge: ['series'] });
}

export function restoreBuiltinMA(chart: any): void {
  chart.setOption({
    series: [
      { name: 'MA5', lineStyle: { opacity: 0.6 } },
      { name: 'MA10', lineStyle: { opacity: 0.6 } },
      { name: 'MA20', lineStyle: { opacity: 0.6 } },
    ],
  });
}

// ============ 数据同步 ============

export function detectKlineLengthChange(chart: any, lastLength: number): number | null {
  const option = chart.getOption();
  const xAxis0 = option.xAxis as Array<{ data?: unknown[] }> | undefined;
  if (!xAxis0?.[0]?.data) return null;
  const currentLength = xAxis0[0].data.length;
  return currentLength !== lastLength ? currentLength : null;
}

export function rebuildAllCachedOverlays(
  chart: any,
  paramGroups: ParamGroup[],
  strategy: StrategyConfig,
): Map<string, CachedOverlay> {
  const klineData = getKlineDataFromChart(chart);
  const newCache = new Map<string, CachedOverlay>();

  let colorIndex = 0;
  for (const group of paramGroups) {
    if (!group.enabled) continue;
    const seriesDefs = buildOverlaySeriesForGroup(group, strategy, klineData, colorIndex);
    newCache.set(group.id, {
      paramsHash: hashParams(group.params),
      seriesDefs,
    });
    colorIndex++;
  }

  return newCache;
}
