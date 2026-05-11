/**
 * K线图技术指标叠加层 — React Hook
 *
 * 管理 overlay 缓存、生命周期、activeGroupId 监听、
 * toggleChipPanel Monkey-Patch、dataZoom 事件监听、
 * 以及 ECharts 'finished' 事件恢复机制。
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
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
  /** K线图就绪信号（klineLoaded: false → true 时触发初始预计算） */
  chartReady: boolean;
  /** 所有参数组 */
  paramGroups: ParamGroup[];
  /** 当前选中的策略配置 */
  strategy: StrategyConfig | undefined;
}

interface UseKlineOverlayReturn {
  /** 当前聚焦的参数组 ID（null = 未选中） */
  activeGroupId: string | null;
  /** 设置聚焦参数组 */
  setActiveGroupId: (id: string | null) => void;
  /** 是否隐藏 kline_chart.js 内置 MA 线 */
  shouldHideBuiltinMA: boolean;
  /** 切换内置 MA 线显隐 */
  setShouldHideBuiltinMA: (hide: boolean) => void;
}

/** 获取 ECharts 实例（由 kline_chart.js 管理） */
function getChartInstance(): any {
  if (typeof window === 'undefined') return null;
  const dom = document.getElementById('mainChart');
  if (!dom) return null;
  return (window as any).echarts?.getInstanceByDom(dom) ?? null;
}

export function useKlineOverlay(
  options: UseKlineOverlayOptions,
): UseKlineOverlayReturn {
  const { chartReady, paramGroups, strategy } = options;

  const [activeGroupId, setActiveGroupId] = useState<string | null>(null);
  const [shouldHideBuiltinMA, setShouldHideBuiltinMA] = useState(false);

  // Refs for callback access (avoid stale closures)
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
  const onDataZoomRef = useRef<(() => void) | null>(null);
  const originalToggleChip = useRef<(() => void) | null>(null);

  // 缓存 chart 实例引用（用于清理 finished 事件监听）
  const chartInstanceRef = useRef<any>(null);

  // ===== chartReady → 轮询等待 ECharts 就绪 → 初始化 + 注册 finished 事件 =====
  // kline_chart.js 在 requestAnimationFrame 中异步渲染，chartReady 变为 true 时
  // #mainChart 和 echarts.init() 可能尚未完成，因此用轮询等待。
  const prevChartReady = useRef(false);
  useEffect(() => {
    if (!chartReady || !strategy || prevChartReady.current) return;
    prevChartReady.current = true;

    let attempts = 0;
    const MAX_ATTEMPTS = 50; // 50 × 100ms = 5 秒

    const interval = setInterval(() => {
      const chart = getChartInstance();
      attempts++;

      if (chart) {
        clearInterval(interval);
        chartInstanceRef.current = chart;

        // --- 初始预计算 ---
        const klineData = getKlineDataFromChart(chart);
        if (klineData.length > 0) {
          const newCache = rebuildAllCachedOverlays(chart, paramGroups, strategy);
          overlayCache.current = newCache;

          const option = chart.getOption();
          const xAxis0 = option.xAxis as Array<{ data?: unknown[] }> | undefined;
          if (xAxis0?.[0]?.data) {
            trackedKlineLengthRef.current = xAxis0[0].data.length;
          }

          if (activeGroupIdRef.current) {
            const cached = newCache.get(activeGroupIdRef.current);
            if (cached) {
              atomicSwapOverlay(chart, cached.seriesDefs);
            }
          }
        }

        // --- 注册 finished 事件（§4.4 恢复机制） ---
        const onFinished = () => {
          // Step A: 重注册 dataZoom（每次渲染后 dataZoom 事件监听可能丢失）
          const currentOnDataZoom = onDataZoomRef.current;
          if (currentOnDataZoom) {
            chart.off('dataZoom', currentOnDataZoom);
            chart.on('dataZoom', currentOnDataZoom);
          }

          // Step B: MA 隐藏（只设 opacity，不设 data: [] 以免清除数据导致无法恢复）
          if (shouldHideBuiltinMARef.current) {
            chart.setOption({
              series: [
                { name: 'MA5', lineStyle: { opacity: 0 } },
                { name: 'MA10', lineStyle: { opacity: 0 } },
                { name: 'MA20', lineStyle: { opacity: 0 } },
              ],
            });
          }

          // Step C: 恢复 overlay（chip panel / resize 等操作可能清空 overlay series）
          if (activeGroupIdRef.current) {
            const cached = overlayCache.current.get(activeGroupIdRef.current);
            if (cached && cached.seriesDefs.length > 0) {
              atomicSwapOverlay(chart, cached.seriesDefs);
            }
          }

          // Step D: 检测数据长度变化
          const xAxis0 = chart.getOption().xAxis as Array<{ data?: unknown[] }> | undefined;
          const newLength = xAxis0?.[0]?.data?.length ?? 0;
          if (newLength > 0 && newLength !== trackedKlineLengthRef.current) {
            trackedKlineLengthRef.current = newLength;
          }
        };

        chart.on('finished', onFinished);

        // 存储清理函数
        chartInstanceRef.current = chart;
        (chartInstanceRef as any)._finishedHandler = onFinished;
      } else if (attempts >= MAX_ATTEMPTS) {
        clearInterval(interval);
      }
    }, 100);

    return () => {
      clearInterval(interval);
      // cleanup finished handler if chart was found
      const c = chartInstanceRef.current;
      const handler = (chartInstanceRef as any)._finishedHandler;
      if (c && handler) {
        c.off('finished', handler);
        (chartInstanceRef as any)._finishedHandler = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartReady, strategy]);

  // ===== 策略切换时清空缓存 =====
  const prevStrategyId = useRef<string | undefined>(undefined);
  useEffect(() => {
    const currentId = strategy?.id;
    if (prevStrategyId.current && prevStrategyId.current !== currentId) {
      overlayCache.current.clear();
      trackedKlineLengthRef.current = 0;
    }
    prevStrategyId.current = currentId;
  }, [strategy]);

  // ===== activeGroupId 变化 → 原子切换 overlay =====
  useEffect(() => {
    const chart = getChartInstance();
    if (!chart || !activeGroupId) return;

    // 参数变更 → 重新计算
    const group = paramGroupsRef.current.find((g) => g.id === activeGroupId);
    const currentStrategy = strategyRef.current;
    if (!group || !currentStrategy) return;

    const klineData = getKlineDataFromChart(chart);
    if (klineData.length === 0) return;

    const newHash = hashParams(group.params);
    const cached = overlayCache.current.get(activeGroupId);

    if (cached && cached.paramsHash === newHash) {
      // 缓存命中：验证数据长度未过期（infinite scroll 可能已加载更多数据）
      const xAxisLen = (chart.getOption().xAxis as Array<{ data?: unknown[] }>)?.[0]?.data?.length ?? 0;
      if (xAxisLen > 0 && cached.seriesDefs[0]?.data.length === xAxisLen) {
        atomicSwapOverlay(chart, cached.seriesDefs);
      } else {
        // 缓存过期：重建所有 overlay 并重新应用
        const freshKlineData = getKlineDataFromChart(chart);
        if (freshKlineData.length > 0) {
          const newCache = rebuildAllCachedOverlays(chart, paramGroupsRef.current, currentStrategy);
          overlayCache.current = newCache;
          const freshCached = newCache.get(activeGroupId);
          if (freshCached) {
            atomicSwapOverlay(chart, freshCached.seriesDefs);
          }
        }
      }
    } else {
      // 缓存未命中或参数变更：重算
      const colorIndex = paramGroupsRef.current
        .filter((g) => g.enabled)
        .findIndex((g) => g.id === activeGroupId);
      const seriesDefs = buildOverlaySeriesForGroup(
        group, currentStrategy, klineData, Math.max(colorIndex, 0),
      );
      overlayCache.current.set(activeGroupId, { paramsHash: newHash, seriesDefs });
      atomicSwapOverlay(chart, seriesDefs);
    }

    // MA 隐藏检查：Grid 0 策略 + 内置 MA 需要隐藏（只设 opacity，不设 data: []）
    if (shouldHideBuiltinMARef.current) {
      const isGrid0 = currentStrategy.id === 'dual_ma' || currentStrategy.id === 'bollinger';
      if (isGrid0) {
        chart.setOption({
          series: [
            { name: 'MA5', lineStyle: { opacity: 0 } },
            { name: 'MA10', lineStyle: { opacity: 0 } },
            { name: 'MA20', lineStyle: { opacity: 0 } },
          ],
        });
      }
    }
  }, [activeGroupId]);

  // ===== activeGroupId 变为 null → 清除 overlay =====
  useEffect(() => {
    if (activeGroupId !== null) return;
    const chart = getChartInstance();
    if (!chart) return;
    clearOverlays(chart);
  }, [activeGroupId]);

  // ===== shouldHideBuiltinMA 变化 =====
  useEffect(() => {
    const chart = getChartInstance();
    if (!chart) return;

    if (shouldHideBuiltinMA) {
      chart.setOption({
        series: [
          { name: 'MA5', lineStyle: { opacity: 0 } },
          { name: 'MA10', lineStyle: { opacity: 0 } },
          { name: 'MA20', lineStyle: { opacity: 0 } },
        ],
      });
    } else {
      chart.setOption({
        series: [
          { name: 'MA5', lineStyle: { opacity: 0.6 } },
          { name: 'MA10', lineStyle: { opacity: 0.6 } },
          { name: 'MA20', lineStyle: { opacity: 0.6 } },
        ],
      });
    }
  }, [shouldHideBuiltinMA]);

  // ===== dataZoom 事件：加载更多历史数据同步 (§6.5) =====
  useEffect(() => {
    const chart = getChartInstance();
    if (!chart) return;

    const onDataZoom = () => {
      const newLength = detectKlineLengthChange(chart, trackedKlineLengthRef.current);
      if (newLength === null) return;

      trackedKlineLengthRef.current = newLength;

      const currentStrategy = strategyRef.current;
      const currentParamGroups = paramGroupsRef.current;
      if (!currentStrategy) return;

      const newCache = rebuildAllCachedOverlays(chart, currentParamGroups, currentStrategy);
      overlayCache.current = newCache;

      // 重新应用当前 overlay
      if (activeGroupIdRef.current) {
        const cached = newCache.get(activeGroupIdRef.current);
        if (cached) {
          atomicSwapOverlay(chart, cached.seriesDefs);
        }
      }
    };

    onDataZoomRef.current = onDataZoom;
    chart.on('dataZoom', onDataZoom);
    return () => { chart.off('dataZoom', onDataZoom); };
  }, [chartReady, paramGroups, strategy]);

  // ===== Monkey-Patch: toggleChipPanel (§5.4) =====
  // chip panel toggle 会通过 setOption 操作图表导致 overlay 丢失。
  // 修复：在 toggle 前注册一次性 finished 监听器，渲染完成后自动恢复 overlay。
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const KlineChart = (window as any).KlineChart;
    if (!KlineChart?.toggleChipPanel) return;

    originalToggleChip.current = KlineChart.toggleChipPanel;

    KlineChart.toggleChipPanel = () => {
      const chart = getChartInstance();

      if (chart && activeGroupIdRef.current) {
        let restored = false;
        const onChipFinished = () => {
          if (restored) return;
          restored = true;
          chart.off('finished', onChipFinished);
          const cached = overlayCache.current.get(activeGroupIdRef.current!);
          if (cached) {
            atomicSwapOverlay(chart, cached.seriesDefs);
          }
        };
        chart.on('finished', onChipFinished);
        originalToggleChip.current!();
      } else {
        originalToggleChip.current!();
      }
    };

    return () => {
      if (originalToggleChip.current) {
        (window as any).KlineChart.toggleChipPanel = originalToggleChip.current;
      }
    };
  }, []);

  // ===== paramGroups 变更时更新缓存（非 focus 的参数组参数变化） =====
  const prevParamHash = useRef<string>('');
  const paramGroupsSnapshot = useMemo(
    () => paramGroups.map((g) => `${g.id}:${hashParams(g.params)}:${g.enabled}`).join(','),
    [paramGroups],
  );

  useEffect(() => {
    if (prevParamHash.current === paramGroupsSnapshot) return;
    prevParamHash.current = paramGroupsSnapshot;

    const chart = getChartInstance();
    if (!chart || !chartReady) return;

    const currentStrategy = strategyRef.current;
    if (!currentStrategy) return;

    // 检查是否有参数确实发生了变化
    let needsRebuild = false;
    for (const group of paramGroups) {
      if (!group.enabled) continue;
      const newHash = hashParams(group.params);
      const cached = overlayCache.current.get(group.id);
      if (!cached || cached.paramsHash !== newHash) {
        needsRebuild = true;
        break;
      }
    }

    if (needsRebuild) {
      const newCache = rebuildAllCachedOverlays(chart, paramGroups, currentStrategy);
      overlayCache.current = newCache;

      if (activeGroupIdRef.current) {
        const cached = newCache.get(activeGroupIdRef.current);
        if (cached) {
          atomicSwapOverlay(chart, cached.seriesDefs);
        }
      }
    }
  }, [paramGroupsSnapshot, chartReady]);

  const setActiveGroupIdWrapped = useCallback((id: string | null) => {
    setActiveGroupId(id);
    // 选中参数组时自动隐藏内置 MA，取消选中时恢复内置 MA
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
