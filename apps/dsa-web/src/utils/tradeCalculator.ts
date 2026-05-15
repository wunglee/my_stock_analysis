/**
 * 交易配对与收益计算
 *
 * 纯前端计算：将 SignalMarker[] 配对为 TradeRecord[]，
 * 并按评估区间过滤计算 P&L。
 */

import type { TradeRecord } from '../types/technicalBacktest';
import type { SignalMarker } from './klineOverlay';

/** 将买卖信号按时间顺序配对为交易记录 */
export function pairSignalsToTrades(signals: SignalMarker[]): TradeRecord[] {
  const trades: TradeRecord[] = [];
  let holding: SignalMarker | null = null;
  let id = 1;

  // 按日期排序（信号本身已按 klineData 顺序生成，这里做防御性排序）
  const sorted = [...signals].sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
  );

  for (const signal of sorted) {
    if (signal.action === 'buy' && !holding) {
      holding = signal;
    } else if (signal.action === 'sell' && holding) {
      const returnPct = ((signal.price - holding.price) / holding.price) * 100;
      const entryTime = new Date(holding.date).getTime();
      const exitTime = new Date(signal.date).getTime();
      const holdDays = Math.round((exitTime - entryTime) / (1000 * 60 * 60 * 24));

      trades.push({
        id: id++,
        entryDate: holding.date,
        entryPrice: holding.price,
        exitDate: signal.date,
        exitPrice: signal.price,
        returnPct,
        pnlAmount: 0,
        holdDays,
        reason: holding.reason,
      });
      holding = null;
    }
  }

  return trades;
}

/** 评估区间内的收益统计 */
export interface RangePnlResult {
  totalReturnPct: number;
  winRate: number;
  tradeCount: number;
  winCount: number;
  lossCount: number;
  avgReturnPct: number;
  avgHoldDays: number;
}

/** 计算指定区间内的收益统计 */
export function calculateRangePnl(
  trades: TradeRecord[],
  rangeStart: string,
  rangeEnd: string,
): RangePnlResult {
  const filtered = trades.filter(
    (t) => t.entryDate >= rangeStart && t.entryDate <= rangeEnd,
  );

  if (filtered.length === 0) {
    return {
      totalReturnPct: 0,
      winRate: 0,
      tradeCount: 0,
      winCount: 0,
      lossCount: 0,
      avgReturnPct: 0,
      avgHoldDays: 0,
    };
  }

  const winCount = filtered.filter((t) => t.returnPct > 0).length;
  const lossCount = filtered.length - winCount;
  const totalReturn = filtered.reduce((sum, t) => sum + t.returnPct, 0);
  const totalHoldDays = filtered.reduce((sum, t) => sum + t.holdDays, 0);

  return {
    totalReturnPct: totalReturn,
    winRate: winCount / filtered.length,
    tradeCount: filtered.length,
    winCount,
    lossCount,
    avgReturnPct: totalReturn / filtered.length,
    avgHoldDays: totalHoldDays / filtered.length,
  };
}
