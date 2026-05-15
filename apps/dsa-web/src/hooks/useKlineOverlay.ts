/**
 * K线图技术指标叠加层 — React Hook（架构 v2）
 *
 * 架构原则：单一 syncToChart() 控制点。所有 ECharts 状态变更都经过此函数，
 * 消除多个 effect 分散调用 setOption 导致的竞态和渲染循环。
 *
 * 3 个 effect（替代旧版 9 个）：
 *   A. Chart 初始化 + 事件注册（finished 恢复 + dataZoom 同步）
 *   B. 状态变更 → syncToChart
 *   C. 策略切换 → 清空缓存
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import type { ParamGroup, StrategyConfig } from '../types/technicalBacktest';
import type { CachedOverlay } from '../utils/klineOverlay';
import {
  atomicSwapOverlay,
  buildOverlaySeriesForGroup,
  clearOverlays,
  detectKlineLengthChange,
  getKlineDataFromChart,
  hashParams,
  rebuildAllCachedOverlays,
} from '../utils/klineOverlay';

interface UseKlineOverlayOptions {
  chartReady: boolean;
  paramGroups: ParamGroup[];
  strategy: StrategyConfig | undefined;
}

interface UseKlineOverlayReturn {
  activeGroupId: string | null;
  setActiveGroupId: (id: string | null) => void;
  shouldHideBuiltinMA: boolean;
  setShouldHideBuiltinMA: (hide: boolean) => void;
}

// ============ 纯工具函数（无 hook 依赖）============

function getChartInstance(): any {
  if (typeof window === 'undefined') return null;
  const dom = document.getElementById('mainChart');
  if (!dom) return null;
  return (window as any).echarts?.getInstanceByDom(dom) ?? null;
}

/** 幂等设置 MA 线透明度，避免无谓的 setOption 触发渲染循环 */
function applyMAVisibility(chart: any, hide: boolean): void {
  const target = hide ? 0 : 0.6;
  const option = chart.getOption();
  if (!option) return;
  const series = option.series as Array<{ name?: string; lineStyle?: { opacity?: number } }>;
  const names = ['MA5', 'MA10', 'MA20'];
  const allAtTarget = names.every((n) => {
    const s = series.find((cs) => cs.name === n);
    return s && (s.lineStyle?.opacity ?? 0.6) === target;
  });
  if (allAtTarget) return;
  chart.setOption({
    series: names.map((name) => ({ name, lineStyle: { opacity: target } })),
  });
}

// ============ Hook ============

export function useKlineOverlay(options: UseKlineOverlayOptions): UseKlineOverlayReturn {
  const { chartReady, paramGroups, strategy } = options;

  const [activeGroupId, setActiveGroupId] = useState<string | null>(null);
  const [shouldHideBuiltinMA, setShouldHideBuiltinMA] = useState(false);

  // ── Refs：所有被 effect/事件回调消费的状态都通过 ref 访问，杜绝闭包过期 ──
  const activeGroupIdRef = useRef(activeGroupId);
  activeGroupIdRef.current = activeGroupId;
  const shouldHideBuiltinMARef = useRef(shouldHideBuiltinMA);
  shouldHideBuiltinMARef.current = shouldHideBuiltinMA;
  const paramGroupsRef = useRef(paramGroups);
  paramGroupsRef.current = paramGroups;
  const strategyRef = useRef(strategy);
  strategyRef.current = strategy;
  const overlayCache = useRef<Map<string, CachedOverlay>>(new Map());
  const trackedKlineLengthRef = useRef(0);
  const chartRef = useRef<any>(null);

  // ── syncToChart：唯一的 ECharts 状态同步入口 ──
  // 函数体直接读取 ref（非 state），无需列入 effect deps。
  function syncToChart(): void {
    const chart = getChartInstance();
    if (!chart) return;
    chartRef.current = chart;

    const gid = activeGroupIdRef.current;
    const curStrategy = strategyRef.current;
    const curGroups = paramGroupsRef.current;

    applyMAVisibility(chart, shouldHideBuiltinMARef.current);

    if (!gid || !curStrategy) {
      clearOverlays(chart);
      return;
    }

    const group = curGroups.find((g) => g.id === gid);
    if (!group) {
      clearOverlays(chart);
      return;
    }

    const klineData = getKlineDataFromChart(chart);
    if (klineData.length === 0) return;

    const newHash = hashParams(group.params);
    const cached = overlayCache.current.get(gid);
    const xAxisLen = ((chart.getOption() as any)?.xAxis as Array<{ data?: unknown[] }>)?.[0]?.data?.length ?? 0;

    if (
      cached &&
      cached.paramsHash === newHash &&
      xAxisLen > 0 &&
      cached.seriesDefs[0]?.data.length === xAxisLen
    ) {
      atomicSwapOverlay(chart, cached.seriesDefs);
    } else {
      const colorIndex = curGroups.filter((g) => g.enabled).findIndex((g) => g.id === gid);
      const seriesDefs = buildOverlaySeriesForGroup(group, curStrategy, klineData, Math.max(colorIndex, 0));
      overlayCache.current.set(gid, { paramsHash: newHash, seriesDefs });
      atomicSwapOverlay(chart, seriesDefs);
    }
  }

  // ═══════════════════════════════════════════════
  // Effect A：Chart 初始化 + finished/dataZoom 事件注册
  // ═══════════════════════════════════════════════
  useEffect(() => {
    if (!chartReady || !strategy) return;

    let cancelled = false;
    let attempts = 0;
    const MAX_ATTEMPTS = 50;

    // rAF 链式轮询：与浏览器渲染周期对齐，找到 chart 即停止
    const tryInit = () => {
      if (cancelled) return;
      const chart = getChartInstance();

      if (chart) {
        chartRef.current = chart;

        // chart 实例可能尚未完成首次 setOption，getOption() 返回 null 或缺少 xAxis
        const option = chart.getOption();
        if (!option || !option.xAxis) {
          if (++attempts < MAX_ATTEMPTS) requestAnimationFrame(tryInit);
          return;
        }

        // 记录初始 K 线长度
        const xAxis0 = option.xAxis as Array<{ data?: unknown[] }>;
        if (xAxis0?.[0]?.data) {
          trackedKlineLengthRef.current = xAxis0[0].data.length;
        }

        // 初始同步（处理 activeGroupId 在 chart 就绪前已设置的情况）
        syncToChart();

        // finished 事件：kline_chart.js 通过 setOption 清除 overlay 后自动恢复
        // 同时检测 overlay 数据长度是否与当前 xAxis 对齐（lazyUpdate 可能导致 onDataZoom 错过重建）
        const onFinished = () => {
          const gid = activeGroupIdRef.current;
          if (!gid) return;
          const cached = overlayCache.current.get(gid);
          if (!cached || cached.seriesDefs.length === 0) return;

          const series = chart.getOption().series as Array<{ name?: string }>;
          const firstDefName = cached.seriesDefs[0].name;
          const overlayExists = series.some((s) => s.name === firstDefName);

          // 检测 xAxis 长度是否与 overlay 数据对齐
          const xAxisData = (chart.getOption() as any)?.xAxis?.[0]?.data;
          const xAxisLen = xAxisData?.length ?? 0;
          const overlayLen = cached.seriesDefs[0]?.data?.length ?? 0;
          const isAligned = xAxisLen === 0 || overlayLen === xAxisLen;

          if (!overlayExists) {
            atomicSwapOverlay(chart, cached.seriesDefs);
          } else if (!isAligned) {
            // 数据长度不对齐（通常是 lazyUpdate 加载更多历史数据后），清除缓存让 syncToChart 重建
            overlayCache.current.delete(gid);
            syncToChart();
          }
        };
        chart.on('finished', onFinished);
        (chartRef as any)._onFinished = onFinished;

        // dataZoom 事件：用户缩放/滚动加载更多历史数据时重建缓存
        const onDataZoom = () => {
          const newLen = detectKlineLengthChange(chart, trackedKlineLengthRef.current);
          if (newLen === null) return;
          trackedKlineLengthRef.current = newLen;

          const curStrategy = strategyRef.current;
          const curGroups = paramGroupsRef.current;
          if (!curStrategy) return;

          overlayCache.current = rebuildAllCachedOverlays(chart, curGroups, curStrategy);

          const gid = activeGroupIdRef.current;
          if (gid) {
            const entry = overlayCache.current.get(gid);
            if (entry) atomicSwapOverlay(chart, entry.seriesDefs);
          }
        };
        chart.on('dataZoom', onDataZoom);
        (chartRef as any)._onDataZoom = onDataZoom;

        return; // 找到 chart，停止轮询
      }

      if (++attempts < MAX_ATTEMPTS) {
        requestAnimationFrame(tryInit);
      }
    };

    requestAnimationFrame(tryInit);

    return () => {
      cancelled = true;
      const c = chartRef.current;
      if (c) {
        const fh = (chartRef as any)._onFinished;
        const dh = (chartRef as any)._onDataZoom;
        if (fh) c.off('finished', fh);
        if (dh) c.off('dataZoom', dh);
        (chartRef as any)._onFinished = null;
        (chartRef as any)._onDataZoom = null;
      }
    };
    // strategy 变化时重新初始化：清掉旧 handler，用新策略重建
  }, [chartReady, strategy]);

  // ═══════════════════════════════════════════════
  // Effect B：状态变更 → 同步到 chart
  // ═══════════════════════════════════════════════
  useEffect(() => {
    if (!chartRef.current) return;
    syncToChart();
  }, [activeGroupId, paramGroups, shouldHideBuiltinMA]);

  // ═══════════════════════════════════════════════
  // Effect C：策略切换 → 清空缓存
  // ═══════════════════════════════════════════════
  const prevStrategyId = useRef<string | undefined>(undefined);
  useEffect(() => {
    const currentId = strategy?.id;
    if (prevStrategyId.current && prevStrategyId.current !== currentId) {
      overlayCache.current.clear();
      trackedKlineLengthRef.current = 0;
    }
    prevStrategyId.current = currentId;
  }, [strategy]);

  // ── Dev: 暴露调试 API 到 window，供 Playwright 直接调用 setActiveGroupId ──
  useEffect(() => {
    if (typeof window === 'undefined') return;
    (window as any).__debugKlineOverlay = {
      setActiveGroupId: (id: string | null) => {
        setActiveGroupId(id);
        setShouldHideBuiltinMA(id !== null);
      },
      getState: () => {
        const chart = getChartInstance();
        return {
          activeGroupId: activeGroupIdRef.current,
          shouldHideBuiltinMA: shouldHideBuiltinMARef.current,
          overlayCacheSize: overlayCache.current.size,
          seriesCount: chart?.getOption()?.series?.length ?? 0,
          seriesNames: (chart?.getOption()?.series as Array<{ name?: string }>)?.map((s) => s.name) ?? [],
        };
      },
    };
    return () => {
      delete (window as any).__debugKlineOverlay;
    };
    // 仅在 mount/unmount 时执行，内部通过 ref 读取最新状态
  }, []);

  // ── 包装 setter：选中参数组时自动隐藏内置 MA ──
  const setActiveGroupIdWrapped = useCallback((id: string | null) => {
    setActiveGroupId(id);
    setShouldHideBuiltinMA(id !== null);
  }, []);

  const setShouldHideBuiltinMAWrapped = useCallback((hide: boolean) => {
    setShouldHideBuiltinMA(hide);
  }, []);

  return {
    activeGroupId,
    setActiveGroupId: setActiveGroupIdWrapped,
    shouldHideBuiltinMA,
    setShouldHideBuiltinMA: setShouldHideBuiltinMAWrapped,
  };
}
