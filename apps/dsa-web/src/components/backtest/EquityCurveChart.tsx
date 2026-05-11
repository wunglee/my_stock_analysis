import { useEffect, useRef } from 'react';
import type { EquityCurvePoint } from '../../types/technicalBacktest';

interface Props {
  equityCurve: EquityCurvePoint[];
  height?: number;
}

// 从全局 echarts 推断图表实例类型
type EChartsInstance = ReturnType<typeof window.echarts.init>;

interface TooltipParam {
  axisValue?: string;
  color?: string;
  seriesName?: string;
  value?: number;
}

export const EquityCurveChart: React.FC<Props> = ({ equityCurve, height = 260 }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<EChartsInstance | null>(null);

  useEffect(() => {
    if (!containerRef.current || typeof window.echarts === 'undefined') return;
    if (!equityCurve || equityCurve.length === 0) return;

    const echarts = window.echarts;
    if (!chartRef.current) {
      chartRef.current = echarts.init(containerRef.current);
    }

    const dates = equityCurve.map((p) => p.date);
    const strategyValues = equityCurve.map((p) => p.strategyValue);
    const benchmarkValues = equityCurve.map((p) => p.benchmarkValue);

    const finalStrategy = strategyValues[strategyValues.length - 1];
    const finalBenchmark = benchmarkValues[benchmarkValues.length - 1];
    const initialValue = strategyValues[0];
    const strategyReturn = ((finalStrategy - initialValue) / initialValue) * 100;
    const benchmarkReturn = ((finalBenchmark - initialValue) / initialValue) * 100;

    // 中国股市惯例：红涨绿跌（盈利=红色，亏损=绿色）
    const strategyColor = strategyReturn >= 0 ? '#ef4444' : '#22c55e';
    const strategyAreaColor = strategyReturn >= 0
      ? 'rgba(239,68,68,0.15)'
      : 'rgba(34,197,94,0.15)';

    const option = {
      backgroundColor: 'transparent',
      grid: { top: 40, right: 16, bottom: 24, left: 56 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(15,23,42,0.95)',
        borderColor: 'rgba(99,102,241,0.3)',
        textStyle: { color: '#e2e8f0', fontSize: 11 },
        formatter: (params: TooltipParam[]) => {
          const date = params[0]?.axisValue || '';
          let html = `<div style="font-weight:600;margin-bottom:4px">${date}</div>`;
          params.forEach((p) => {
            const color = p.color;
            html += `<div style="display:flex;align-items:center;gap:6px">
              <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color}"></span>
              <span>${p.seriesName}: <strong>${Number(p.value).toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</strong></span>
            </div>`;
          });
          return html;
        },
      },
      legend: {
        data: [
          `策略 ${strategyReturn >= 0 ? '+' : ''}${strategyReturn.toFixed(1)}%`,
          `基准 ${benchmarkReturn >= 0 ? '+' : ''}${benchmarkReturn.toFixed(1)}%`,
        ],
        textStyle: { color: '#94a3b8', fontSize: 11 },
        top: 8,
        right: 8,
      },
      xAxis: {
        type: 'category',
        data: dates,
        axisLine: { lineStyle: { color: 'rgba(148,163,184,0.2)' } },
        axisLabel: { color: '#64748b', fontSize: 10, interval: Math.floor(dates.length / 6) },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: 'rgba(148,163,184,0.08)' } },
        axisLabel: {
          color: '#64748b',
          fontSize: 10,
          formatter: (v: number) => (v >= 10000 ? `${(v / 10000).toFixed(0)}万` : String(v)),
        },
      },
      series: [
        {
          name: `策略 ${strategyReturn >= 0 ? '+' : ''}${strategyReturn.toFixed(1)}%`,
          type: 'line',
          data: strategyValues,
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 2, color: strategyColor },
          itemStyle: { color: strategyColor },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: strategyAreaColor },
                { offset: 1, color: 'rgba(34,197,94,0)' },
              ],
            },
          },
        },
        {
          name: `基准 ${benchmarkReturn >= 0 ? '+' : ''}${benchmarkReturn.toFixed(1)}%`,
          type: 'line',
          data: benchmarkValues,
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 1.5, color: '#64748b', type: 'dashed' },
          itemStyle: { color: '#64748b' },
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
  }, [equityCurve]);

  if (!equityCurve || equityCurve.length === 0) {
    return (
      <div style={{ height }} className="flex items-center justify-center text-xs text-muted-text">
        无收益率数据
      </div>
    );
  }

  return <div ref={containerRef} style={{ width: '100%', height }} />;
};
