/**
 * 评估区间管理 Hook
 *
 * 管理 K线图上评估区间的起止索引，提供拖动交互和像素坐标转换。
 * 区间以 xAxis 数据索引为单位，通过 ECharts convertToPixel / convertFromPixel
 * 与图表像素位置同步。
 */

import { useState, useEffect, useRef, useCallback } from 'react';

function getChartInstance(): any {
  if (typeof window === 'undefined') return null;
  const dom = document.getElementById('mainChart');
  if (!dom) return null;
  return (window as any).echarts?.getInstanceByDom(dom) ?? null;
}

/** 从 chart option 读取 xAxis 日期列表 */
function getXAxisDates(chart: any): string[] {
  const option = chart?.getOption();
  if (!option?.xAxis?.[0]?.data) return [];
  return option.xAxis[0].data as string[];
}

/** 获取当前可视区域的数据索引范围 */
function getVisibleIndexRange(chart: any): { min: number; max: number } | null {
  try {
    const option = chart?.getOption?.();
    const dataZoom = option?.dataZoom?.[0];
    if (!dataZoom) return null;
    const min = typeof dataZoom.startValue === 'number' ? Math.round(dataZoom.startValue) : 0;
    const max = typeof dataZoom.endValue === 'number' ? Math.round(dataZoom.endValue) : 0;
    return { min, max };
  } catch {
    return null;
  }
}

export interface EvaluationRange {
  startIndex: number;
  endIndex: number;
  startDate: string;
  endDate: string;
}

export interface PixelRange {
  left: number;
  width: number;
}

interface UseEvaluationRangeOptions {
  chartReady: boolean;
  klineLoadId: number;
}

interface DragLabel {
  date: string;
  pixelX: number;
}

interface UseEvaluationRangeReturn {
  range: EvaluationRange | null;
  pixelRange: PixelRange | null;
  isDragging: 'start' | 'end' | 'body' | null;
  dragLabel: DragLabel | null;
  handleMouseDown: (target: 'start' | 'end' | 'body', clientX: number) => void;
}

export function useEvaluationRange(
  options: UseEvaluationRangeOptions,
): UseEvaluationRangeReturn {
  const { chartReady, klineLoadId } = options;

  const [range, setRange] = useState<EvaluationRange | null>(null);
  const [pixelRange, setPixelRange] = useState<PixelRange | null>(null);
  const [isDragging, setIsDragging] = useState<'start' | 'end' | 'body' | null>(null);
  const [dragLabel, setDragLabel] = useState<DragLabel | null>(null);

  // Refs for drag state (avoid stale closures in mousemove)
  const rangeRef = useRef(range);
  rangeRef.current = range;
  const isDraggingRef = useRef(isDragging);
  isDraggingRef.current = isDragging;
  const dragStartXRef = useRef(0);
  const dragStartRangeRef = useRef<EvaluationRange | null>(null);

  // ── 初始化默认区间：K线数据的中间 30% ──
  useEffect(() => {
    if (!chartReady) return;

    let cancelled = false;
    let attempts = 0;
    const MAX_ATTEMPTS = 50;

    const tryInit = () => {
      if (cancelled) return;
      const chart = getChartInstance();
      if (!chart) {
        if (++attempts < MAX_ATTEMPTS) requestAnimationFrame(tryInit);
        return;
      }

      const option = chart.getOption();
      if (!option || !option.xAxis) {
        if (++attempts < MAX_ATTEMPTS) requestAnimationFrame(tryInit);
        return;
      }

      const dates = getXAxisDates(chart);
      if (dates.length === 0) {
        if (++attempts < MAX_ATTEMPTS) requestAnimationFrame(tryInit);
        return;
      }

      const len = dates.length;

      // 默认覆盖当前可见的 dataZoom 范围（而非整个数据集）
      // 避免左侧边界落在视口外导致把手不可见
      const dataZoom = option.dataZoom?.[0];
      let startIndex = 0;
      let endIndex = len - 1;
      if (dataZoom) {
        if (typeof dataZoom.startValue === 'number') {
          startIndex = Math.max(0, Math.min(Math.round(dataZoom.startValue), len - 1));
        }
        if (typeof dataZoom.endValue === 'number') {
          endIndex = Math.max(0, Math.min(Math.round(dataZoom.endValue), len - 1));
        }
      }

      setRange({
        startIndex,
        endIndex,
        startDate: dates[startIndex],
        endDate: dates[endIndex],
      });
    };

    requestAnimationFrame(tryInit);

    return () => {
      cancelled = true;
    };
  }, [chartReady, klineLoadId]);

  // ── 更新 pixelRange：将索引转换为像素坐标 ──
  const updatePixelRange = useCallback(() => {
    const chart = getChartInstance();
    const curRange = rangeRef.current;
    // dataZoom 动画期间可能暂时拿不到 chart 或 range，保持旧值避免闪烁/消失
    if (!chart || !curRange) return;

    const dates = getXAxisDates(chart);
    if (dates.length === 0) return;

    // 获取可视区域范围
    const visible = getVisibleIndexRange(chart);
    const visMin = visible?.min ?? 0;
    const visMax = visible?.max ?? dates.length - 1;

    // clamp indices to valid range
    let startIdx = Math.max(0, Math.min(curRange.startIndex, dates.length - 1));
    let endIdx = Math.max(0, Math.min(curRange.endIndex, dates.length - 1));

    // 如果面板超出可视区域，自动拉回（保持宽度不变）
    const panelWidth = endIdx - startIdx;
    let adjusted = false;
    if (endIdx < visMin) {
      // 整个面板在可视区域左侧 → 拉到左边界
      startIdx = visMin;
      endIdx = Math.min(visMin + panelWidth, visMax);
      adjusted = true;
    } else if (startIdx > visMax) {
      // 整个面板在可视区域右侧 → 拉到右边界
      endIdx = visMax;
      startIdx = Math.max(visMax - panelWidth, visMin);
      adjusted = true;
    } else if (startIdx < visMin) {
      // 左边界超出 → 向右拉
      startIdx = visMin;
      endIdx = Math.min(visMin + panelWidth, visMax);
      adjusted = true;
    } else if (endIdx > visMax) {
      // 右边界超出 → 向左拉
      endIdx = visMax;
      startIdx = Math.max(visMax - panelWidth, visMin);
      adjusted = true;
    }

    // 确保最小宽度
    if (endIdx - startIdx < 5) {
      endIdx = Math.min(startIdx + 5, visMax);
      startIdx = Math.max(endIdx - 5, visMin);
      adjusted = true;
    }

    // 如果调整过 range，同步更新状态
    if (adjusted && (startIdx !== curRange.startIndex || endIdx !== curRange.endIndex)) {
      const newRange: EvaluationRange = {
        startIndex: startIdx,
        endIndex: endIdx,
        startDate: dates[startIdx],
        endDate: dates[endIdx],
      };
      setRange(newRange);
      rangeRef.current = newRange;
    }

    const startPoint = chart.convertToPixel({ seriesIndex: 0 }, [dates[startIdx], 0]);
    const endPoint = chart.convertToPixel({ seriesIndex: 0 }, [dates[endIdx], 0]);

    // ECharts category axis returns [x, y] array; value axis may return number
    const startPixel = Array.isArray(startPoint) ? startPoint[0] : startPoint;
    const endPixel = Array.isArray(endPoint) ? endPoint[0] : endPoint;

    if (
      typeof startPixel === 'number' &&
      typeof endPixel === 'number' &&
      !Number.isNaN(startPixel) &&
      !Number.isNaN(endPixel)
    ) {
      const left = startPixel;
      const width = Math.max(0, endPixel - startPixel);
      setPixelRange({ left, width });
    }
  }, []);

  // ── 监听 chart 事件，更新 pixelRange ──
  useEffect(() => {
    if (!chartReady || !range) return;

    const chart = getChartInstance();
    if (!chart) return;

    const onUpdate = () => {
      // 延迟两帧确保 ECharts 已完成布局（dataZoom 动画期间状态可能不稳定）
      requestAnimationFrame(() => requestAnimationFrame(updatePixelRange));
    };

    chart.on('finished', onUpdate);
    chart.on('dataZoom', onUpdate);
    window.addEventListener('resize', onUpdate);

    // 初始更新
    onUpdate();

    return () => {
      chart.off('finished', onUpdate);
      chart.off('dataZoom', onUpdate);
      window.removeEventListener('resize', onUpdate);
    };
  }, [chartReady, range, updatePixelRange]);

  // ── 拖动逻辑 ──
  const handleMouseDown = useCallback(
    (target: 'start' | 'end' | 'body', clientX: number) => {
      setIsDragging(target);
      isDraggingRef.current = target;
      dragStartXRef.current = clientX;
      dragStartRangeRef.current = rangeRef.current ? { ...rangeRef.current } : null;
    },
    [],
  );

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const chart = getChartInstance();
      const startRange = dragStartRangeRef.current;
      if (!chart || !startRange) return;

      const dates = getXAxisDates(chart);
      if (dates.length === 0) return;

      const chartDom = document.getElementById('mainChart');
      if (!chartDom) return;

      const rect = chartDom.getBoundingClientRect();
      const xInChart = e.clientX - rect.left;

      // 将像素坐标转换为数据索引
      const point = chart.convertFromPixel({ seriesIndex: 0 }, [xInChart, 0]);
      let newIndex: number;

      if (Array.isArray(point) && typeof point[0] === 'number') {
        // category axis: convertFromPixel returns [index, value]
        newIndex = Math.round(point[0]);
      } else if (typeof point === 'number') {
        newIndex = Math.round(point);
      } else {
        return;
      }

      // clamp to valid range
      newIndex = Math.max(0, Math.min(newIndex, dates.length - 1));

      let newStart = startRange.startIndex;
      let newEnd = startRange.endIndex;

      const visible = getVisibleIndexRange(chart);
      const visMin = visible?.min ?? 0;
      const visMax = visible?.max ?? dates.length - 1;

      if (isDraggingRef.current === 'start') {
        // 限制在可视区域内，且至少保留 5 根 K线
        newStart = Math.max(visMin, Math.min(newIndex, startRange.endIndex - 5));
      } else if (isDraggingRef.current === 'end') {
        newEnd = Math.min(visMax, Math.max(newIndex, startRange.startIndex + 5));
      } else if (isDraggingRef.current === 'body') {
        const dx = e.clientX - dragStartXRef.current;
        const startPoint = chart.convertToPixel(
          { seriesIndex: 0 },
          [dates[startRange.startIndex], 0],
        );
        const endPoint = chart.convertToPixel(
          { seriesIndex: 0 },
          [dates[startRange.endIndex], 0],
        );
        const startPixel = Array.isArray(startPoint) ? startPoint[0] : startPoint;
        const endPixel = Array.isArray(endPoint) ? endPoint[0] : endPoint;
        if (typeof startPixel !== 'number' || typeof endPixel !== 'number') return;

        const width = endPixel - startPixel;
        const offsetRatio = width > 0 ? dx / width : 0;
        const indexOffset = Math.round(
          (startRange.endIndex - startRange.startIndex) * offsetRatio,
        );

        newStart = startRange.startIndex + indexOffset;
        newEnd = startRange.endIndex + indexOffset;

        // clamp to visible range
        const rangeWidth = newEnd - newStart;
        if (newStart < visMin) {
          newStart = visMin;
          newEnd = Math.min(visMin + rangeWidth, visMax);
        }
        if (newEnd > visMax) {
          newEnd = visMax;
          newStart = Math.max(visMax - rangeWidth, visMin);
        }
      }

      // ensure valid ordering
      if (newStart >= newEnd) {
        if (isDraggingRef.current === 'start') newStart = newEnd - 5;
        else if (isDraggingRef.current === 'end') newEnd = newStart + 5;
      }

      newStart = Math.max(0, Math.min(newStart, dates.length - 1));
      newEnd = Math.max(0, Math.min(newEnd, dates.length - 1));

      const newRange: EvaluationRange = {
        startIndex: newStart,
        endIndex: newEnd,
        startDate: dates[newStart],
        endDate: dates[newEnd],
      };

      setRange(newRange);
      rangeRef.current = newRange;

      // 更新拖动标签位置
      const targetIndex = isDraggingRef.current === 'start' ? newStart : newEnd;
      const labelPoint = chart.convertToPixel(
        { seriesIndex: 0 },
        [dates[targetIndex], 0],
      );
      const pixelX = Array.isArray(labelPoint) ? labelPoint[0] : labelPoint;
      if (typeof pixelX === 'number') {
        setDragLabel({ date: dates[targetIndex], pixelX });
      }
    };

    const handleMouseUp = () => {
      setIsDragging(null);
      isDraggingRef.current = null;
      setDragLabel(null);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, updatePixelRange]);

  return {
    range,
    pixelRange,
    isDragging,
    dragLabel,
    handleMouseDown,
  };
}
