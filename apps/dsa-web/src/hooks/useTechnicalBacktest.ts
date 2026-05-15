import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { backtestApi } from '../api/backtest';
import { getParsedApiError } from '../api/error';
import type { ParsedApiError } from '../api/error';
import type { StrategyConfig, StrategyParameter, ParamGroup, ParamGroupResult, BacktestTemplateItem } from '../types/technicalBacktest';
import { useSessionState, isNonEmptyArray } from './useSessionState';
import { useTechnicalTemplates } from './useTechnicalTemplates';
import {
  calcDualMASignals,
  calcMACDSignals,
  calcRSISignals,
  calcBollingerSignals,
  getKlineDataFromChart,
} from '../utils/klineOverlay';
import { pairSignalsToTrades } from '../utils/tradeCalculator';
import type { SignalMarker, KlineBar } from '../utils/klineOverlay';
import type { TradeRecord, EquityCurvePoint, TechnicalBacktestStockResult, TechnicalSignal } from '../types/technicalBacktest';

/** 从策略参数定义构建默认参数值映射 */
function buildDefaultParams(parameters: StrategyParameter[]): Record<string, number | boolean> {
  const params: Record<string, number | boolean> = {};
  parameters.forEach((p) => { params[p.key] = p.defaultValue; });
  return params;
}

/** 从股票代码输入中提取标准化代码（去掉市场后缀，取第一个） */
function extractNormalizedStockCode(codesInput: string): string | null {
  const tokens = codesInput.split(/[,，\s]+/).filter(Boolean);
  if (tokens.length === 0) return null;
  return tokens[0].trim().replace(/\.(SH|SZ|HK|US)$/i, '');
}

/** 获取 ECharts 实例 */
function getChartInstance(): any {
  if (typeof window === 'undefined') return null;
  const dom = document.getElementById('mainChart');
  if (!dom) return null;
  return (window as any).echarts?.getInstanceByDom(dom) ?? null;
}

/** 根据策略和参数组计算买卖信号 */
function calculateSignals(strategy: StrategyConfig, group: ParamGroup, klineData: KlineBar[]): SignalMarker[] {
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

/** SignalMarker → TechnicalSignal */
function toTechnicalSignals(markers: SignalMarker[]): TechnicalSignal[] {
  return markers.map((m) => ({
    date: m.date,
    action: m.action,
    entryPrice: m.price,
    stopLoss: null,
    takeProfit: null,
    reasons: m.reason ? [m.reason] : [],
    confidence: 1,
  }));
}

/** 构建权益曲线（简化版：每笔交易退出时应用收益） */
function buildEquityCurve(klineData: KlineBar[], trades: TradeRecord[]): EquityCurvePoint[] {
  if (klineData.length === 0) return [];

  const initialValue = 100_000;
  const points: EquityCurvePoint[] = [];

  // 按退出日期聚合收益
  const exitMap = new Map<string, number>();
  trades.forEach((t) => {
    const existing = exitMap.get(t.exitDate) ?? 0;
    exitMap.set(t.exitDate, existing + t.returnPct);
  });

  let currentValue = initialValue;
  const firstClose = klineData[0].close;

  for (const bar of klineData) {
    const dayReturn = exitMap.get(bar.date);
    if (dayReturn != null) {
      currentValue = currentValue * (1 + dayReturn / 100);
    }

    const benchmarkValue = initialValue * (bar.close / firstClose);

    points.push({
      date: bar.date,
      strategyValue: currentValue,
      benchmarkValue,
    });
  }

  return points;
}

/** 构建单个参数组的即时回测结果 */
function buildInstantResult(
  group: ParamGroup,
  strategy: StrategyConfig,
  klineData: KlineBar[],
  stockCode: string,
): ParamGroupResult {
  const signals = calculateSignals(strategy, group, klineData);
  const trades = pairSignalsToTrades(signals);
  const equityCurve = buildEquityCurve(klineData, trades);

  const winTrades = trades.filter((t) => t.returnPct > 0);
  const totalReturn = trades.reduce((sum, t) => sum + t.returnPct, 0);
  const avgReturn = trades.length > 0 ? totalReturn / trades.length : 0;

  // 计算最大回撤
  let maxDrawdown = 0;
  let peak = 100_000;
  equityCurve.forEach((p) => {
    if (p.strategyValue > peak) peak = p.strategyValue;
    const dd = ((peak - p.strategyValue) / peak) * 100;
    if (dd > maxDrawdown) maxDrawdown = dd;
  });

  const stockResult: TechnicalBacktestStockResult = {
    code: stockCode,
    stockName: stockCode,
    dateRange: `${klineData[0]?.date} ~ ${klineData[klineData.length - 1]?.date}`,
    totalSignals: signals.length,
    winRate: trades.length > 0 ? (winTrades.length / trades.length) * 100 : 0,
    avgReturn,
    maxDrawdown,
    klineData,
    rules: [],
    signals: toTechnicalSignals(signals),
    evaluations: [],
    equityCurve,
    trades,
  };

  return {
    group,
    status: 'success',
    stockResult,
    equityCurve,
    trades,
  };
}

// ============ sessionStorage Keys ============

const STORAGE_KEY_RESULTS = 'technical_backtest_results';
const STORAGE_KEY_PARAM_GROUPS = 'technical_backtest_param_groups';
const STORAGE_KEY_STRATEGY_ID = 'technical_backtest_strategy_id';

interface UseTechnicalBacktestOptions {
  technicalCodes: string;
  technicalStartDate: string;
  technicalEndDate: string;
  technicalEvalDays: string;
  klineLoaded?: boolean;
  klineLoadId?: number;
}

interface UseTechnicalBacktestReturn {
  strategies: StrategyConfig[];
  selectedStrategyId: string;
  setSelectedStrategyId: (id: string) => void;
  selectedStrategy: StrategyConfig | undefined;
  strategyError: ParsedApiError | null;

  paramGroups: ParamGroup[];
  invalidGroupIds: Set<string>;
  addParamGroup: () => void;
  removeParamGroup: (id: string) => void;
  duplicateParamGroup: (id: string) => void;
  updateParamValue: (groupId: string, key: string, value: number | boolean) => void;
  updateGroupName: (groupId: string, name: string) => void;
  toggleGroupEnabled: (groupId: string) => void;
  setInvalidGroupIds: (ids: Set<string>) => void;

  batchResults: ParamGroupResult[] | null;
  isBatchRunning: boolean;
  technicalError: ParsedApiError | null;
  setTechnicalError: (err: ParsedApiError | null) => void;
  handleRunBatch: () => Promise<void>;

  templates: BacktestTemplateItem[];
  isLoadingTemplates: boolean;
  loadTemplates: () => Promise<void>;
  saveAsTemplate: (name: string) => Promise<void>;
  deleteTemplate: (id: number) => Promise<void>;
  loadTemplate: (template: BacktestTemplateItem) => void;
}

export function useTechnicalBacktest(
  options: UseTechnicalBacktestOptions,
): UseTechnicalBacktestReturn {
  const { technicalCodes, klineLoaded, klineLoadId } = options;

  // 策略列表（服务端数据，不持久化到 sessionStorage）
  const [strategies, setStrategies] = useState<StrategyConfig[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useSessionState<string>(STORAGE_KEY_STRATEGY_ID, { defaultValue: '' });
  const [strategyError, setStrategyError] = useState<ParsedApiError | null>(null);

  // 参数组（sessionStorage 持久化）
  const [paramGroups, setParamGroups] = useSessionState<ParamGroup[]>(STORAGE_KEY_PARAM_GROUPS, {
    defaultValue: [],
    validate: isNonEmptyArray,
  });
  const [invalidGroupIds, setInvalidGroupIds] = useState<Set<string>>(new Set());

  // 回测结果
  const [batchResults, setBatchResults] = useState<ParamGroupResult[] | null>(null);
  const [isBatchRunning, setIsBatchRunning] = useState(false);
  const [technicalError, setTechnicalError] = useState<ParsedApiError | null>(null);

  // 模板 CRUD（独立 Hook）
  const {
    templates,
    isLoadingTemplates,
    loadTemplates,
    saveAsTemplate,
    deleteTemplate,
    loadTemplate,
  } = useTechnicalTemplates(
    { selectedStrategyId, paramGroups },
    setParamGroups,
    setBatchResults,
    setTechnicalError,
  );

  // 自动持久化跟踪
  const paramsSourceRef = useRef<'user' | 'backend'>('user');
  const lastLoadedKeyRef = useRef<string>('');
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 用 ref 跟踪 technicalCodes 最新值，避免 effect 对每次按键重跑
  const technicalCodesRef = useRef(technicalCodes);
  technicalCodesRef.current = technicalCodes;

  // Bug 修复：没有加载 K 线时清除回测结果（结果必须与 K 线配对）
  useEffect(() => {
    if (!klineLoaded) {
      setBatchResults(null);
      try { sessionStorage.removeItem(STORAGE_KEY_RESULTS); } catch { /* 静默降级 */ }
    }
  }, [klineLoaded]);

  // 加载策略列表（仅在挂载时执行）
  useEffect(() => {
    backtestApi.getStrategies()
      .then((configs) => {
        setStrategies(configs);
        if (configs.length > 0 && !selectedStrategyId) {
          setSelectedStrategyId(configs[0].id);
        }
      })
      .catch((err) => setStrategyError(getParsedApiError(err)));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 回测结果变化时持久化到 sessionStorage
  useEffect(() => {
    if (batchResults) {
      try { sessionStorage.setItem(STORAGE_KEY_RESULTS, JSON.stringify(batchResults)); } catch { /* 静默降级 */ }
    }
  }, [batchResults]);

  // 跟踪前一个策略 ID，区分"初始加载"和"用户主动切换策略"
  const prevStrategyId = useRef<string>('');

  // 切换策略时初始化默认参数组
  useEffect(() => {
    if (!selectedStrategyId || strategies.length === 0) return;
    const strategy = strategies.find((s) => s.id === selectedStrategyId);
    if (!strategy) return;

    const isUserSwitch = prevStrategyId.current !== '' && prevStrategyId.current !== selectedStrategyId;
    prevStrategyId.current = selectedStrategyId;

    if (isUserSwitch) {
      paramsSourceRef.current = 'user';
      setParamGroups([
        {
          id: crypto.randomUUID(),
          name: '参数组 1',
          enabled: true,
          params: buildDefaultParams(strategy.parameters),
        },
      ]);
      setBatchResults(null);
      try { sessionStorage.removeItem(STORAGE_KEY_RESULTS); } catch { /* 静默降级 */ }
    } else if (paramGroups.length === 0) {
      paramsSourceRef.current = 'user';
      setParamGroups([
        {
          id: crypto.randomUUID(),
          name: '参数组 1',
          enabled: true,
          params: buildDefaultParams(strategy.parameters),
        },
      ]);
    } else if (paramsSourceRef.current !== 'backend') {
      const strategyKeys = new Set(strategy.parameters.map((p) => p.key));
      const hasMismatch = paramGroups.some((g) => {
        const keys = Object.keys(g.params);
        return keys.length !== strategyKeys.size || !keys.every((k) => strategyKeys.has(k));
      });
      if (hasMismatch) {
        setParamGroups([
          {
            id: crypto.randomUUID(),
            name: '参数组 1',
            enabled: true,
            params: buildDefaultParams(strategy.parameters),
          },
        ]);
      }
    }
  }, [selectedStrategyId, strategies]);

  // ============ 自动加载回测会话 ============

  useEffect(() => {
    if (!klineLoaded || !selectedStrategyId) return;
    const stockCode = extractNormalizedStockCode(technicalCodesRef.current);
    if (!stockCode) return;

    const loadKey = `${stockCode}:${selectedStrategyId}`;
    if (loadKey === lastLoadedKeyRef.current) return;
    lastLoadedKeyRef.current = loadKey;

    backtestApi.loadSession(stockCode, selectedStrategyId)
      .then((session) => {
        if (session) {
          paramsSourceRef.current = 'backend';
          if (session.paramGroups && session.paramGroups.length > 0) {
            setParamGroups(session.paramGroups);
          }
          if (session.batchResults) {
            const validResults = session.batchResults.filter((r) => r?.group?.id);
            if (validResults.length > 0) setBatchResults(validResults);
          }
        }
      })
      .catch(() => {
        // 网络错误时降级到 sessionStorage，不覆盖当前状态
      });
  }, [klineLoaded, klineLoadId, selectedStrategyId]);

  // ============ 自动保存回测会话 ============

  // 参数组变化时 debounced 保存（只保存参数，不覆盖已有结果）
  useEffect(() => {
    if (!klineLoaded) return;
    const stockCode = extractNormalizedStockCode(technicalCodesRef.current);
    if (!stockCode || !selectedStrategyId) return;

    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      backtestApi.saveSession({
        stockCode,
        strategyId: selectedStrategyId,
        paramGroups,
      }).catch(() => { /* 静默降级 */ });
    }, 2000);

    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, [paramGroups]);

  // 回测结果到达时立即保存
  useEffect(() => {
    if (!klineLoaded || !batchResults) return;
    const stockCode = extractNormalizedStockCode(technicalCodesRef.current);
    if (!stockCode || !selectedStrategyId) return;

    backtestApi.saveSession({
      stockCode,
      strategyId: selectedStrategyId,
      paramGroups,
      batchResults,
    }).catch(() => { /* 静默降级 */ });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchResults]);

  const selectedStrategy = useMemo(
    () => strategies.find((s) => s.id === selectedStrategyId),
    [strategies, selectedStrategyId],
  );

  const addParamGroup = useCallback(() => {
    if (!selectedStrategy || paramGroups.length >= 6) return;
    const nextNum = paramGroups.length + 1;
    setParamGroups((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        name: `参数组 ${nextNum}`,
        enabled: true,
        params: buildDefaultParams(selectedStrategy.parameters),
      },
    ]);
  }, [selectedStrategy, paramGroups.length, setParamGroups]);

  const removeParamGroup = useCallback((id: string) => {
    setParamGroups((prev) => prev.filter((g) => g.id !== id));
  }, [setParamGroups]);

  const duplicateParamGroup = useCallback((id: string) => {
    if (!selectedStrategy || paramGroups.length >= 6) return;
    const group = paramGroups.find((g) => g.id === id);
    if (!group) return;
    setParamGroups((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        name: `${group.name} (副本)`,
        enabled: true,
        params: { ...group.params },
      },
    ]);
  }, [selectedStrategy, paramGroups, setParamGroups]);

  const updateParamValue = useCallback((
    groupId: string,
    key: string,
    value: number | boolean,
  ) => {
    setParamGroups((prev) =>
      prev.map((g) =>
        g.id === groupId ? { ...g, params: { ...g.params, [key]: value } } : g,
      ),
    );
  }, [setParamGroups]);

  const updateGroupName = useCallback((groupId: string, name: string) => {
    setParamGroups((prev) =>
      prev.map((g) => (g.id === groupId ? { ...g, name } : g)),
    );
  }, [setParamGroups]);

  const toggleGroupEnabled = useCallback((groupId: string) => {
    setParamGroups((prev) =>
      prev.map((g) =>
        g.id === groupId ? { ...g, enabled: !g.enabled } : g,
      ),
    );
  }, [setParamGroups]);

  /** 前端即时计算所有启用参数组的回测结果 */
  const calculateInstantResults = useCallback(() => {
    const stockCode = extractNormalizedStockCode(technicalCodesRef.current);
    if (!stockCode || !selectedStrategy) return;

    const chart = getChartInstance();
    if (!chart) return;

    const klineData = getKlineDataFromChart(chart);
    if (!klineData.length) return;

    const enabledGroups = paramGroups.filter((g) => g.enabled);
    if (enabledGroups.length === 0) return;

    const invalidEnabled = enabledGroups.filter((g) => invalidGroupIds.has(g.id));
    if (invalidEnabled.length > 0) {
      setTechnicalError({
        title: '参数校验失败',
        message: `存在 ${invalidEnabled.length} 个参数组的配置不满足策略约束条件，请检查红色标记的参数组`,
        rawMessage: '参数组校验失败',
        status: 400,
        category: 'http_error',
      });
      return;
    }

    setIsBatchRunning(true);
    setTechnicalError(null);

    try {
      const results = enabledGroups.map((group) =>
        buildInstantResult(group, selectedStrategy, klineData, stockCode),
      );
      setBatchResults(results);
    } catch (err) {
      setTechnicalError({
        title: '计算错误',
        message: err instanceof Error ? err.message : '回测计算失败',
        rawMessage: String(err),
        status: 500,
        category: 'http_error',
      });
    } finally {
      setIsBatchRunning(false);
    }
  }, [paramGroups, invalidGroupIds, selectedStrategy]);

  // 参数变化时自动触发即时计算
  useEffect(() => {
    if (!klineLoaded || !selectedStrategy || paramGroups.length === 0) return;
    // debounce 300ms 避免频繁参数调整时重复计算
    const timer = setTimeout(() => {
      calculateInstantResults();
    }, 300);
    return () => clearTimeout(timer);
  }, [klineLoaded, selectedStrategy, paramGroups, klineLoadId, calculateInstantResults]);

  const handleRunBatch = useCallback(async () => {
    const codes = technicalCodes
      .split(/[,，\s]+/)
      .map((c) => c.trim())
      .filter(Boolean);
    if (codes.length === 0) return;
    if (codes.length > 1) {
      setTechnicalError({
        title: '参数错误',
        message: '当前仅支持单股回测，请输入一个股票代码',
        rawMessage: '当前仅支持单股回测，请输入一个股票代码',
        status: 400,
        category: 'missing_params',
      });
      return;
    }

    const enabledGroups = paramGroups.filter((g) => g.enabled);
    if (enabledGroups.length === 0) {
      setTechnicalError({
        title: '参数不足',
        message: '请至少启用一个参数组',
        rawMessage: '请至少启用一个参数组',
        status: 400,
        category: 'missing_params',
      });
      return;
    }

    const invalidEnabled = enabledGroups.filter((g) => invalidGroupIds.has(g.id));
    if (invalidEnabled.length > 0) {
      setTechnicalError({
        title: '参数校验失败',
        message: `存在 ${invalidEnabled.length} 个参数组的配置不满足策略约束条件，请检查红色标记的参数组`,
        rawMessage: '参数组校验失败',
        status: 400,
        category: 'http_error',
      });
      return;
    }

    // 前端即时计算（不再调用后端）
    calculateInstantResults();
  }, [paramGroups, invalidGroupIds, calculateInstantResults]);

  return {
    strategies,
    selectedStrategyId,
    setSelectedStrategyId,
    selectedStrategy,
    strategyError,
    paramGroups,
    invalidGroupIds,
    addParamGroup,
    removeParamGroup,
    duplicateParamGroup,
    updateParamValue,
    updateGroupName,
    toggleGroupEnabled,
    setInvalidGroupIds,
    batchResults,
    isBatchRunning,
    technicalError,
    setTechnicalError,
    handleRunBatch,
    templates,
    isLoadingTemplates,
    loadTemplates,
    saveAsTemplate,
    deleteTemplate,
    loadTemplate,
  };
}
