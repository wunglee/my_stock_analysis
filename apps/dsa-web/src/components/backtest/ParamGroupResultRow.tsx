import { useEffect, useRef } from 'react';
import { Badge } from '../common';
import type { ParamGroupResult, KlineData, TechnicalSignal } from '../../types/technicalBacktest';

interface Props {
  result: ParamGroupResult;
}

// 从全局 echarts 推断图表实例类型
type EChartsInstance = ReturnType<typeof window.echarts.init>;

interface MarkPoint {
  coord: [number, number];
  value: string;
  itemStyle: { color: string };
}

const MiniKline: React.FC<{
  klineData: KlineData[];
  signals: TechnicalSignal[];
  height?: number;
}> = ({ klineData, signals, height = 220 }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<EChartsInstance | null>(null);

  useEffect(() => {
    if (!containerRef.current || typeof window.echarts === 'undefined') return;
    if (!klineData || klineData.length === 0) return;

    const echarts = window.echarts;
    if (!chartRef.current) {
      chartRef.current = echarts.init(containerRef.current);
    }

    const candleData = klineData.map((d) => [d.open, d.close, d.low, d.high]);
    const dates = klineData.map((d) => d.date);

    // 构建买卖信号 markPoint
    const signalMap = new Map<string, TechnicalSignal>();
    signals.forEach((s) => signalMap.set(s.date, s));

    const buyPoints: MarkPoint[] = [];
    const sellPoints: MarkPoint[] = [];
    klineData.forEach((d, idx) => {
      const sig = signalMap.get(d.date);
      if (sig) {
        const point: MarkPoint = {
          coord: [idx, d.high],
          value: sig.action === 'buy' ? 'B' : 'S',
          itemStyle: {
            color: sig.action === 'buy' ? '#ef4444' : '#22c55e',
          },
        };
        if (sig.action === 'buy') buyPoints.push(point);
        else if (sig.action === 'sell') sellPoints.push(point);
      }
    });

    const option = {
      backgroundColor: 'transparent',
      grid: { top: 8, right: 8, bottom: 20, left: 8 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLine: { lineStyle: { color: 'rgba(148,163,184,0.15)' } },
        axisLabel: { color: '#475569', fontSize: 9, interval: Math.floor(dates.length / 4) },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: 'rgba(148,163,184,0.06)' } },
        axisLabel: { color: '#475569', fontSize: 9 },
      },
      dataZoom: [{ type: 'inside', start: 0, end: 100 }],
      series: [
        {
          type: 'candlestick',
          data: candleData,
          itemStyle: {
            color: '#ef4444',
            color0: '#22c55e',
            borderColor: '#ef4444',
            borderColor0: '#22c55e',
          },
          markPoint: {
            symbol: 'pin',
            symbolSize: 28,
            label: {
              fontSize: 10,
              fontWeight: 'bold',
              color: '#fff',
            },
            data: [...buyPoints, ...sellPoints],
          },
        },
      ],
    };

    chartRef.current.setOption(option, true);

    const handleResize = () => chartRef.current?.resize();
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartRef.current) {
        chartRef.current.dispose();
        chartRef.current = null;
      }
    };
  }, [klineData, signals]);

  if (!klineData || klineData.length === 0) {
    return (
      <div style={{ height }} className="flex items-center justify-center text-xs text-muted-text">
        无K线数据
      </div>
    );
  }

  return <div ref={containerRef} style={{ width: '100%', height }} />;
};

export const ParamGroupResultRow: React.FC<Props> = ({ result }) => {
  const { group, stockResult, equityCurve, trades } = result;

  if (!stockResult) {
    return (
      <div className="rounded-xl border border-white/5 bg-card/30 overflow-hidden animate-fade-in">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/5 bg-white/[0.02]">
          <div className="flex items-center gap-3">
            <Badge variant="info" glow>{group.name}</Badge>
            <span className="text-xs text-warning">
              {result.status === 'insufficient_data' ? '数据不足' : result.status === 'error' ? result.errorMessage || '回测失败' : '无数据'}
            </span>
          </div>
        </div>
      </div>
    );
  }

  // 计算概览指标
  const finalEquity = equityCurve[equityCurve.length - 1];
  const initialValue = equityCurve[0]?.strategyValue || 100_000;
  const strategyReturn = finalEquity
    ? ((finalEquity.strategyValue - initialValue) / initialValue) * 100
    : 0;
  const benchmarkReturn = finalEquity
    ? ((finalEquity.benchmarkValue - initialValue) / initialValue) * 100
    : 0;
  const winTrades = trades.filter((t) => t.returnPct > 0).length;
  const tradeWinRate = trades.length > 0 ? (winTrades / trades.length) * 100 : 0;

  // 计算最大回撤
  let maxDrawdown = 0;
  let peak = initialValue;
  equityCurve.forEach((p) => {
    if (p.strategyValue > peak) peak = p.strategyValue;
    const dd = ((peak - p.strategyValue) / peak) * 100;
    if (dd > maxDrawdown) maxDrawdown = dd;
  });

  return (
    <div className="rounded-xl border border-white/5 bg-card/30 overflow-hidden animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/5 bg-white/[0.02]">
        <div className="flex items-center gap-3">
          <Badge variant="info" glow>{group.name}</Badge>
          <span className="text-xs text-muted-text">{stockResult.code} · {stockResult.stockName}</span>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="text-muted-text">信号 <span className="text-secondary-text font-mono">{stockResult.totalSignals}</span></span>
          <span className="text-muted-text">交易 <span className="text-secondary-text font-mono">{trades.length}</span></span>
          <span className={strategyReturn >= 0 ? 'text-danger' : 'text-success'}>
            策略收益 <span className="font-mono">{strategyReturn >= 0 ? '+' : ''}{strategyReturn.toFixed(1)}%</span>
          </span>
          <span className="text-muted-text">
            基准 <span className="font-mono">{benchmarkReturn >= 0 ? '+' : ''}{benchmarkReturn.toFixed(1)}%</span>
          </span>
        </div>
      </div>

      {/* Content: left K-line + right stats & equity curve */}
      <div className="flex flex-col lg:flex-row">
        {/* Left: Mini K-line with signals */}
        <div className="lg:w-[35%] border-b lg:border-b-0 lg:border-r border-white/5 p-3">
          <MiniKline klineData={stockResult.klineData || []} signals={stockResult.signals || []} />
        </div>

        {/* Right: Stats + Equity curve */}
        <div className="lg:w-[65%] p-3 space-y-3">
          {/* Stats row */}
          <div className="grid grid-cols-4 gap-2">
            <div className="rounded-lg bg-white/[0.03] px-3 py-2 text-center">
              <div className="text-[10px] text-muted-text uppercase">胜率</div>
              <div className={`text-sm font-mono font-semibold ${tradeWinRate >= 50 ? 'text-success' : 'text-warning'}`}>
                {tradeWinRate.toFixed(0)}%
              </div>
            </div>
            <div className="rounded-lg bg-white/[0.03] px-3 py-2 text-center">
              <div className="text-[10px] text-muted-text uppercase">最大回撤</div>
              <div className="text-sm font-mono font-semibold text-success">
                -{maxDrawdown.toFixed(1)}%
              </div>
            </div>
            <div className="rounded-lg bg-white/[0.03] px-3 py-2 text-center">
              <div className="text-[10px] text-muted-text uppercase">平均持仓</div>
              <div className="text-sm font-mono font-semibold text-secondary-text">
                {trades.length > 0
                  ? `${(trades.reduce((s, t) => s + t.holdDays, 0) / trades.length).toFixed(0)}天`
                  : '--'}
              </div>
            </div>
            <div className="rounded-lg bg-white/[0.03] px-3 py-2 text-center">
              <div className="text-[10px] text-muted-text uppercase">超额收益</div>
              <div className={`text-sm font-mono font-semibold ${strategyReturn - benchmarkReturn >= 0 ? 'text-danger' : 'text-success'}`}>
                {strategyReturn - benchmarkReturn >= 0 ? '+' : ''}{(strategyReturn - benchmarkReturn).toFixed(1)}%
              </div>
            </div>
          </div>

          {/* Recent trades mini table */}
          {trades.length > 0 && (
            <div className="backtest-table-wrapper max-h-32 overflow-y-auto">
              <table className="backtest-table min-w-[400px] w-full text-[10px]">
                <thead className="backtest-table-head">
                  <tr>
                    <th className="backtest-table-head-cell py-1">买入日</th>
                    <th className="backtest-table-head-cell py-1">买入价</th>
                    <th className="backtest-table-head-cell py-1">卖出日</th>
                    <th className="backtest-table-head-cell py-1">卖出价</th>
                    <th className="backtest-table-head-cell py-1">收益率</th>
                    <th className="backtest-table-head-cell py-1">持仓</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t) => (
                    <tr key={t.id} className="backtest-table-row">
                      <td className="backtest-table-cell py-1">{t.entryDate}</td>
                      <td className="backtest-table-cell py-1 font-mono">{t.entryPrice.toFixed(2)}</td>
                      <td className="backtest-table-cell py-1">{t.exitDate}</td>
                      <td className="backtest-table-cell py-1 font-mono">{t.exitPrice.toFixed(2)}</td>
                      <td className={`backtest-table-cell py-1 font-mono ${t.returnPct > 0 ? 'text-danger' : t.returnPct < 0 ? 'text-success' : ''}`}>
                        {t.returnPct > 0 ? '+' : ''}{t.returnPct.toFixed(1)}%
                      </td>
                      <td className="backtest-table-cell py-1">{t.holdDays}天</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
