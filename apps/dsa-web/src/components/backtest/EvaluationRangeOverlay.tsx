/**
 * 评估区间覆盖层
 *
 * 在 K 线图上渲染半透明可拖动区间，显示当前参数组在区间内的收益。
 * 使用 React Portal 渲染到 #mainChart 容器内，确保像素坐标与 ECharts 完全对齐。
 */

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useEvaluationRange } from '../../hooks/useEvaluationRange';
import { pairSignalsToTrades, calculateRangePnl } from '../../utils/tradeCalculator';
import type { RangePnlResult } from '../../utils/tradeCalculator';
import type { SignalMarker, KlineBar } from '../../utils/klineOverlay';
import {
  calcDualMASignals,
  calcMACDSignals,
  calcRSISignals,
  calcBollingerSignals,
  getKlineDataFromChart,
} from '../../utils/klineOverlay';
import type { ParamGroup, StrategyConfig } from '../../types/technicalBacktest';

interface EvaluationRangeOverlayProps {
  chartReady: boolean;
  klineLoadId: number;
  strategy: StrategyConfig | undefined;
  paramGroups: ParamGroup[];
  activeGroupId: string | null;
}

function getChartInstance(): any {
  if (typeof window === 'undefined') return null;
  const dom = document.getElementById('mainChart');
  if (!dom) return null;
  return (window as any).echarts?.getInstanceByDom(dom) ?? null;
}

/** 根据策略和参数组计算买卖信号 */
function calculateSignals(
  strategy: StrategyConfig,
  group: ParamGroup,
  klineData: KlineBar[],
): SignalMarker[] {
  switch (strategy.id) {
    case 'dual_ma': {
      const short = Number(group.params.shortPeriod ?? 5);
      const long = Number(group.params.longPeriod ?? 20);
      return calcDualMASignals(klineData, short, long);
    }
    case 'macd': {
      const fast = Number(group.params.fast ?? 12);
      const slow = Number(group.params.slow ?? 26);
      const signal = Number(group.params.signal ?? 9);
      return calcMACDSignals(klineData, fast, slow, signal);
    }
    case 'rsi': {
      const period = Number(group.params.period ?? 14);
      const oversold = Number(group.params.oversold ?? 30);
      const overbought = Number(group.params.overbought ?? 70);
      return calcRSISignals(klineData, period, oversold, overbought);
    }
    case 'bollinger': {
      const period = Number(group.params.period ?? 20);
      const stdDev = Number(group.params.stdDev ?? 2);
      return calcBollingerSignals(klineData, period, stdDev);
    }
    default:
      return [];
  }
}

/** P&L 结果标签 */
function PnlLabel({ result }: { result: RangePnlResult }) {
  const winRatePct = (result.winRate * 100).toFixed(0);
  // A 股习惯：盈利红色，亏损绿色
  const returnColor = result.totalReturnPct > 0 ? '#ef4444' : result.totalReturnPct < 0 ? '#22c55e' : '#9ca3af';

  return (
    <div
      style={{
        position: 'absolute',
        top: 8,
        right: 8,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(4px)',
        padding: '6px 10px',
        borderRadius: 6,
        fontSize: 11,
        lineHeight: 1.5,
        color: '#e5e7eb',
        whiteSpace: 'nowrap',
        pointerEvents: 'none',
        border: '1px solid rgba(255,255,255,0.1)',
      }}
    >
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <span style={{ color: '#9ca3af' }}>区间收益</span>
        <span style={{ color: returnColor, fontWeight: 600 }}>
          {result.totalReturnPct > 0 ? '+' : ''}{result.totalReturnPct.toFixed(1)}%
        </span>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <span style={{ color: '#9ca3af' }}>胜率</span>
        <span>{winRatePct}%</span>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <span style={{ color: '#9ca3af' }}>交易次数</span>
        <span>{result.tradeCount}次</span>
        {result.tradeCount > 0 && (
          <span style={{ color: '#6b7280', fontSize: 10 }}>
            ({result.winCount}赢/{result.lossCount}亏)
          </span>
        )}
      </div>
    </div>
  );
}

export function EvaluationRangeOverlay({
  chartReady,
  klineLoadId,
  strategy,
  paramGroups,
  activeGroupId,
}: EvaluationRangeOverlayProps) {
  const { range, pixelRange, isDragging, dragLabel, handleMouseDown } = useEvaluationRange({
    chartReady,
    klineLoadId,
  });

  const [pnlResult, setPnlResult] = useState<RangePnlResult | null>(null);

  // 计算区间内 P&L
  useEffect(() => {
    if (!chartReady || !strategy || !range) {
      setPnlResult(null);
      return;
    }

    const chart = getChartInstance();
    if (!chart) {
      setPnlResult(null);
      return;
    }

    const klineData = getKlineDataFromChart(chart);
    if (!klineData.length) {
      setPnlResult(null);
      return;
    }

    // 使用 activeGroup 或第一个启用的参数组
    const targetGroup = activeGroupId
      ? paramGroups.find((g) => g.id === activeGroupId && g.enabled)
      : paramGroups.find((g) => g.enabled);

    if (!targetGroup) {
      setPnlResult(null);
      return;
    }

    const signals = calculateSignals(strategy, targetGroup, klineData);
    const trades = pairSignalsToTrades(signals);
    const result = calculateRangePnl(trades, range.startDate, range.endDate);
    setPnlResult(result);
  }, [chartReady, strategy, paramGroups, activeGroupId, range, klineLoadId]);

  // 获取 Portal 目标容器（不缓存，因为 mainChart 由 kline_chart.js 动态创建）
  const portalTarget = typeof document !== 'undefined' ? document.getElementById('mainChart') : null;

  if (!portalTarget || !pixelRange || !range) return null;

  return createPortal(
    <div
      style={{
        position: 'absolute',
        left: pixelRange.left,
        width: pixelRange.width,
        top: '5%',
        bottom: '47%',
        pointerEvents: 'none',
        zIndex: 10,
      }}
    >
      {/* 半透明背景层 */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundColor: 'rgba(59, 130, 246, 0.18)',
          borderLeft: '2px dashed rgba(96, 165, 250, 0.8)',
          borderRight: '2px dashed rgba(96, 165, 250, 0.8)',
          pointerEvents: 'auto',
          cursor: isDragging === 'body' ? 'grabbing' : 'grab',
        }}
        onMouseDown={(e) => handleMouseDown('body', e.clientX)}
        title={`评估区间: ${range.startDate} ~ ${range.endDate}`}
      >
        {/* 顶部中心标签 */}
        <div
          style={{
            position: 'absolute',
            top: 4,
            left: '50%',
            transform: 'translateX(-50%)',
            backgroundColor: 'rgba(37, 99, 235, 0.85)',
            color: '#fff',
            fontSize: 10,
            padding: '2px 8px',
            borderRadius: 4,
            whiteSpace: 'nowrap',
            pointerEvents: 'none',
            fontWeight: 500,
          }}
        >
          评估区间
        </div>
      </div>

      {/* 左边界拖动把手 */}
      <div
        style={{
          position: 'absolute',
          left: -8,
          top: 0,
          bottom: 0,
          width: 16,
          cursor: 'col-resize',
          pointerEvents: 'auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
        onMouseDown={(e) => {
          e.stopPropagation();
          handleMouseDown('start', e.clientX);
        }}
      >
        <div
          style={{
            width: 5,
            height: 40,
            borderRadius: 3,
            backgroundColor: '#3b82f6',
            border: '1.5px solid rgba(255, 255, 255, 0.8)',
            boxShadow: '0 0 6px rgba(59, 130, 246, 0.6)',
          }}
        />
      </div>

      {/* 右边界拖动把手 */}
      <div
        style={{
          position: 'absolute',
          right: -8,
          top: 0,
          bottom: 0,
          width: 16,
          cursor: 'col-resize',
          pointerEvents: 'auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
        onMouseDown={(e) => {
          e.stopPropagation();
          handleMouseDown('end', e.clientX);
        }}
      >
        <div
          style={{
            width: 5,
            height: 40,
            borderRadius: 3,
            backgroundColor: '#3b82f6',
            border: '1.5px solid rgba(255, 255, 255, 0.8)',
            boxShadow: '0 0 6px rgba(59, 130, 246, 0.6)',
          }}
        />
      </div>

      {/* P&L 结果标签 */}
      {pnlResult && <PnlLabel result={pnlResult} />}

      {/* 拖动时的时间标签 */}
      {dragLabel && (
        <div
          style={{
            position: 'absolute',
            left: dragLabel.pixelX - 40,
            top: -28,
            width: 80,
            textAlign: 'center',
            pointerEvents: 'none',
            zIndex: 20,
          }}
        >
          <div
            style={{
              backgroundColor: 'rgba(0, 0, 0, 0.85)',
              color: '#fff',
              fontSize: 11,
              padding: '2px 6px',
              borderRadius: 4,
              whiteSpace: 'nowrap',
              border: '1px solid rgba(59, 130, 246, 0.5)',
            }}
          >
            {dragLabel.date}
          </div>
        </div>
      )}
    </div>,
    portalTarget,
  );
}
