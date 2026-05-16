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
  type: 'line' | 'bar' | 'scatter';
  data: (number | string | (string | number)[] | { value: (string | number)[]; symbol?: string; symbolRotate?: number; symbolSize?: number; itemStyle?: { color: string } })[];
  xAxisIndex: 0 | 1;
  yAxisIndex: 0 | 1;
  animation: false;
  lineStyle?: { color: string; type?: 'solid' | 'dashed'; width?: number; opacity?: number };
  itemStyle?: { color: string };
  areaStyle?: { color: string; opacity?: number };
  symbol?: string;
  symbolSize?: number;
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

// ============ 买卖信号计算 ============
// 与后端 src/services/backtest/strategies/*.py 逻辑完全一致

export interface SignalMarker {
  date: string;
  action: 'buy' | 'sell';
  price: number;
  reason: string;
  index?: number; // 在 KlineData 中的索引，用于图表精确定位
}

/** 双均线策略信号：金叉买入 / 死叉卖出 */
export function calcDualMASignals(
  klineData: KlineBar[],
  shortPeriod: number,
  longPeriod: number,
): SignalMarker[] {
  const signals: SignalMarker[] = [];
  const maShort = calcMA(klineData, shortPeriod);
  const maLong = calcMA(klineData, longPeriod);

  for (let i = 1; i < klineData.length; i++) {
    const prevShort = maShort[i - 1];
    const prevLong = maLong[i - 1];
    const currShort = maShort[i];
    const currLong = maLong[i];

    if (typeof prevShort !== 'number' || typeof prevLong !== 'number' ||
        typeof currShort !== 'number' || typeof currLong !== 'number') continue;

    // 金叉：前一日短期 <= 长期，当日短期 > 长期
    if (prevShort <= prevLong && currShort > currLong) {
      signals.push({
        date: klineData[i].date,
        action: 'buy',
        price: klineData[i].low,
        reason: `金叉：短期均线(${shortPeriod}日)上穿长期均线(${longPeriod}日)`,
        index: i,
      });
    }
    // 死叉：前一日短期 >= 长期，当日短期 < 长期
    else if (prevShort >= prevLong && currShort < currLong) {
      signals.push({
        date: klineData[i].date,
        action: 'sell',
        price: klineData[i].high,
        reason: `死叉：短期均线(${shortPeriod}日)下穿长期均线(${longPeriod}日)`,
        index: i,
      });
    }
  }
  return signals;
}

/** MACD 策略信号：DIF/DEA 金叉死叉 */
export function calcMACDSignals(
  klineData: KlineBar[],
  fast: number,
  slow: number,
  signal: number,
): SignalMarker[] {
  const signals: SignalMarker[] = [];
  const emaFast = calcEMA(klineData, fast);
  const emaSlow = calcEMA(klineData, slow);

  // DIF = EMA_fast - EMA_slow
  const dif: (number | string)[] = [];
  for (let i = 0; i < klineData.length; i++) {
    if (typeof emaFast[i] === 'number' && typeof emaSlow[i] === 'number') {
      dif.push(+((emaFast[i] as number) - (emaSlow[i] as number)).toFixed(4));
    } else {
      dif.push('-');
    }
  }

  // DEA = EMA of DIF
  const deaK = 2 / (signal + 1);
  const dea: (number | string)[] = [];
  let deaValue = 0;
  let firstDiff = false;
  for (let i = 0; i < dif.length; i++) {
    if (typeof dif[i] !== 'number') {
      dea.push('-');
    } else if (!firstDiff) {
      deaValue = dif[i] as number;
      firstDiff = true;
      dea.push(+deaValue.toFixed(4));
    } else {
      deaValue = (dif[i] as number) * deaK + deaValue * (1 - deaK);
      dea.push(+deaValue.toFixed(4));
    }
  }

  for (let i = 1; i < klineData.length; i++) {
    const prevDiff = dif[i - 1];
    const prevDea = dea[i - 1];
    const currDiff = dif[i];
    const currDea = dea[i];

    if (typeof prevDiff !== 'number' || typeof prevDea !== 'number' ||
        typeof currDiff !== 'number' || typeof currDea !== 'number') continue;

    // 金叉：前一日 DIF <= DEA，当日 DIF > DEA
    if (prevDiff <= prevDea && currDiff > currDea) {
      signals.push({
        date: klineData[i].date,
        action: 'buy',
        price: klineData[i].low,
        reason: `金叉：DIF(${currDiff.toFixed(4)})上穿DEA(${currDea.toFixed(4)})`,
        index: i,
      });
    }
    // 死叉：前一日 DIF >= DEA，当日 DIF < DEA
    else if (prevDiff >= prevDea && currDiff < currDea) {
      signals.push({
        date: klineData[i].date,
        action: 'sell',
        price: klineData[i].high,
        reason: `死叉：DIF(${currDiff.toFixed(4)})下穿DEA(${currDea.toFixed(4)})`,
        index: i,
      });
    }
  }
  return signals;
}

/** RSI 策略信号：超卖回升买入 / 超买回落卖出 */
export function calcRSISignals(
  klineData: KlineBar[],
  period: number,
  oversold: number,
  overbought: number,
): SignalMarker[] {
  const signals: SignalMarker[] = [];
  const rsi = calcRSI(klineData, period);

  for (let i = 1; i < klineData.length; i++) {
    const prevRsi = rsi[i - 1];
    const currRsi = rsi[i];

    if (typeof prevRsi !== 'number' || typeof currRsi !== 'number') continue;

    // 从超卖区回升 → buy
    if (prevRsi <= oversold && currRsi > oversold) {
      signals.push({
        date: klineData[i].date,
        action: 'buy',
        price: klineData[i].low,
        reason: `RSI从超卖区回升 (${prevRsi.toFixed(1)} → ${currRsi.toFixed(1)})`,
        index: i,
      });
    }
    // 从超买区回落 → sell
    else if (prevRsi >= overbought && currRsi < overbought) {
      signals.push({
        date: klineData[i].date,
        action: 'sell',
        price: klineData[i].high,
        reason: `RSI从超买区回落 (${prevRsi.toFixed(1)} → ${currRsi.toFixed(1)})`,
        index: i,
      });
    }
  }
  return signals;
}

/** 布林带策略信号：价格触及上/下轨 */
export function calcBollingerSignals(
  klineData: KlineBar[],
  period: number,
  stdDev: number,
): SignalMarker[] {
  const signals: SignalMarker[] = [];
  const { upper, lower } = calcBollinger(klineData, period, stdDev);

  for (let i = 1; i < klineData.length; i++) {
    const prevClose = klineData[i - 1].close;
    const currClose = klineData[i].close;
    const prevUpper = upper[i - 1];
    const currUpper = upper[i];
    const prevLower = lower[i - 1];
    const currLower = lower[i];

    if (typeof prevUpper !== 'number' || typeof currUpper !== 'number' ||
        typeof prevLower !== 'number' || typeof currLower !== 'number') continue;

    // 上穿上轨 → sell（价格从下方向上穿到上轨之上）
    if (prevClose <= prevUpper && currClose > currUpper) {
      signals.push({
        date: klineData[i].date,
        action: 'sell',
        price: klineData[i].high,
        reason: `价格触及上轨 (收盘${currClose.toFixed(2)} > 上轨${currUpper.toFixed(2)})`,
        index: i,
      });
    }
    // 下穿下轨 → buy（价格从上方向下穿到下轨之下）
    else if (prevClose >= prevLower && currClose < currLower) {
      signals.push({
        date: klineData[i].date,
        action: 'buy',
        price: klineData[i].low,
        reason: `价格触及下轨 (收盘${currClose.toFixed(2)} < 下轨${currLower.toFixed(2)})`,
        index: i,
      });
    }
  }
  return signals;
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

/** 计算信号标记在图表上的显示价格，避免与 K 线柱子重叠 */
function getSignalDisplayPrice(s: SignalMarker, klineData: KlineBar[]): number {
  const bar = s.index != null && s.index >= 0 && s.index < klineData.length
    ? klineData[s.index]
    : klineData.find((k) => k.date === s.date);
  if (!bar) return s.price;
  const range = bar.high - bar.low;
  const offset = Math.max(range * 1.2, bar.close * 0.02);
  return s.action === 'buy' ? bar.low - offset : bar.high + offset;
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
      const short = group.params.shortPeriod as number;
      const long = group.params.longPeriod as number;
      const maShort = calcMA(klineData, short);
      const maLong = calcMA(klineData, long);
      const signals = calcDualMASignals(klineData, short, long);
      return [
        {
          name: `${prefix}_MA(${short})`,
          type: 'line',
          data: maShort,
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          symbol: 'none',
          lineStyle: { color, type: 'solid', width: 1.5 },
        },
        {
          name: `${prefix}_MA(${long})`,
          type: 'line',
          data: maLong,
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          symbol: 'none',
          lineStyle: { color, type: 'dashed', width: 1.5 },
        },
        {
          name: `${prefix}_BUY`,
          type: 'scatter',
          data: signals.filter((s) => s.action === 'buy').map((s) => ({
            value: [s.index ?? s.date, getSignalDisplayPrice(s, klineData)],
            symbol: 'triangle',
            symbolSize: 18,
            itemStyle: { color: '#ef4444', borderColor: '#fff', borderWidth: 2, shadowBlur: 4, shadowColor: 'rgba(0,0,0,0.4)' },
          })),
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          symbol: 'triangle',
          symbolSize: 14,
        },
        {
          name: `${prefix}_SELL`,
          type: 'scatter',
          data: signals.filter((s) => s.action === 'sell').map((s) => ({
            value: [s.index ?? s.date, getSignalDisplayPrice(s, klineData)],
            symbol: 'triangle',
            symbolRotate: 180,
            symbolSize: 18,
            itemStyle: { color: '#22c55e', borderColor: '#fff', borderWidth: 2, shadowBlur: 4, shadowColor: 'rgba(0,0,0,0.4)' },
          })),
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          symbol: 'triangle',
          symbolSize: 14,
        },
      ];
    }

    case 'bollinger': {
      const period = group.params.period as number;
      const stdDev = group.params.stdDev as number;
      const { upper, middle, lower } = calcBollinger(klineData, period, stdDev);
      const signals = calcBollingerSignals(klineData, period, stdDev);
      return [
        {
          name: `${prefix}_Upper(${period},${stdDev})`,
          type: 'line',
          data: upper,
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          symbol: 'none',
          lineStyle: { color, type: 'solid', width: 1 },
        },
        {
          name: `${prefix}_Middle(${period})`,
          type: 'line',
          data: middle,
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          symbol: 'none',
          lineStyle: { color, type: 'dashed', width: 1 },
        },
        {
          name: `${prefix}_Lower(${period},${stdDev})`,
          type: 'line',
          data: lower,
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          symbol: 'none',
          lineStyle: { color, type: 'solid', width: 1 },
          areaStyle: { color, opacity: 0.08 },
        },
        {
          name: `${prefix}_BUY`,
          type: 'scatter',
          data: signals.filter((s) => s.action === 'buy').map((s) => ({
            value: [s.index ?? s.date, getSignalDisplayPrice(s, klineData)],
            symbol: 'triangle',
            symbolSize: 18,
            itemStyle: { color: '#ef4444', borderColor: '#fff', borderWidth: 2, shadowBlur: 4, shadowColor: 'rgba(0,0,0,0.4)' },
          })),
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          symbol: 'triangle',
          symbolSize: 14,
        },
        {
          name: `${prefix}_SELL`,
          type: 'scatter',
          data: signals.filter((s) => s.action === 'sell').map((s) => ({
            value: [s.index ?? s.date, getSignalDisplayPrice(s, klineData)],
            symbol: 'triangle',
            symbolRotate: 180,
            symbolSize: 18,
            itemStyle: { color: '#22c55e', borderColor: '#fff', borderWidth: 2, shadowBlur: 4, shadowColor: 'rgba(0,0,0,0.4)' },
          })),
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          symbol: 'triangle',
          symbolSize: 14,
        },
      ];
    }

    case 'macd': {
      const fast = group.params.fast as number;
      const slow = group.params.slow as number;
      const signal = group.params.signal as number;
      const { diff, dea, histogram } = calcMACD(klineData, fast, slow, signal);
      const signals = calcMACDSignals(klineData, fast, slow, signal);
      return [
        {
          name: `${prefix}_DIFF(${fast},${slow})`,
          type: 'line',
          data: diff,
          xAxisIndex: 1,
          yAxisIndex: 1,
          animation: false,
          symbol: 'none',
          lineStyle: { color, type: 'solid', width: 1 },
        },
        {
          name: `${prefix}_DEA(${fast},${slow},${signal})`,
          type: 'line',
          data: dea,
          xAxisIndex: 1,
          yAxisIndex: 1,
          animation: false,
          symbol: 'none',
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
        {
          name: `${prefix}_BUY`,
          type: 'scatter',
          data: signals.filter((s) => s.action === 'buy').map((s) => ({
            value: [s.index ?? s.date, getSignalDisplayPrice(s, klineData)],
            symbol: 'triangle',
            symbolSize: 18,
            itemStyle: { color: '#ef4444', borderColor: '#fff', borderWidth: 2, shadowBlur: 4, shadowColor: 'rgba(0,0,0,0.4)' },
          })),
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          symbol: 'triangle',
          symbolSize: 14,
        },
        {
          name: `${prefix}_SELL`,
          type: 'scatter',
          data: signals.filter((s) => s.action === 'sell').map((s) => ({
            value: [s.index ?? s.date, getSignalDisplayPrice(s, klineData)],
            symbol: 'triangle',
            symbolRotate: 180,
            symbolSize: 18,
            itemStyle: { color: '#22c55e', borderColor: '#fff', borderWidth: 2, shadowBlur: 4, shadowColor: 'rgba(0,0,0,0.4)' },
          })),
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          symbol: 'triangle',
          symbolSize: 14,
        },
      ];
    }

    case 'rsi': {
      const period = group.params.period as number;
      const oversold = (group.params.oversold as number) ?? 30;
      const overbought = (group.params.overbought as number) ?? 70;
      const rsi = calcRSI(klineData, period);
      const ref70 = new Array(klineData.length).fill(70);
      const ref30 = new Array(klineData.length).fill(30);
      const signals = calcRSISignals(klineData, period, oversold, overbought);
      return [
        {
          name: `${prefix}_RSI(${period})`,
          type: 'line',
          data: rsi,
          xAxisIndex: 1,
          yAxisIndex: 1,
          animation: false,
          symbol: 'none',
          lineStyle: { color, type: 'solid', width: 1.5 },
        },
        {
          name: `${prefix}_RSI_70`,
          type: 'line',
          data: ref70,
          xAxisIndex: 1,
          yAxisIndex: 1,
          animation: false,
          symbol: 'none',
          lineStyle: { color: '#ef4444', type: 'dashed', width: 0.5, opacity: 0.5 },
        },
        {
          name: `${prefix}_RSI_30`,
          type: 'line',
          data: ref30,
          xAxisIndex: 1,
          yAxisIndex: 1,
          animation: false,
          symbol: 'none',
          lineStyle: { color: '#22c55e', type: 'dashed', width: 0.5, opacity: 0.5 },
        },
        {
          name: `${prefix}_BUY`,
          type: 'scatter',
          data: signals.filter((s) => s.action === 'buy').map((s) => ({
            value: [s.index ?? s.date, getSignalDisplayPrice(s, klineData)],
            symbol: 'triangle',
            symbolSize: 18,
            itemStyle: { color: '#ef4444', borderColor: '#fff', borderWidth: 2, shadowBlur: 4, shadowColor: 'rgba(0,0,0,0.4)' },
          })),
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          symbol: 'triangle',
          symbolSize: 14,
        },
        {
          name: `${prefix}_SELL`,
          type: 'scatter',
          data: signals.filter((s) => s.action === 'sell').map((s) => ({
            value: [s.index ?? s.date, getSignalDisplayPrice(s, klineData)],
            symbol: 'triangle',
            symbolRotate: 180,
            symbolSize: 18,
            itemStyle: { color: '#22c55e', borderColor: '#fff', borderWidth: 2, shadowBlur: 4, shadowColor: 'rgba(0,0,0,0.4)' },
          })),
          xAxisIndex: 0,
          yAxisIndex: 0,
          animation: false,
          symbol: 'triangle',
          symbolSize: 14,
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
  const option = chart.getOption();
  if (!option || !option.series) return;
  const currentSeries = option.series as Array<{ name?: string }>;
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
  if (!option) return null;
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
