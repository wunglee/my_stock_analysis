import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { backtestApi } from '../api/backtest';
import { getParsedApiError } from '../api/error';
import type { ParsedApiError } from '../api/error';
import type { StrategyConfig, StrategyParameter, ParamGroup, ParamGroupResult, BacktestTemplateItem } from '../types/technicalBacktest';

/** 从策略参数定义构建默认参数值映射 */
function buildDefaultParams(parameters: StrategyParameter[]): Record<string, number | boolean> {
  const params: Record<string, number | boolean> = {};
  parameters.forEach((p) => { params[p.key] = p.defaultValue; });
  return params;
}

// ============ sessionStorage 持久化工具 ============

const STORAGE_KEY_RESULTS = 'technical_backtest_results';
const STORAGE_KEY_PARAM_GROUPS = 'technical_backtest_param_groups';
const STORAGE_KEY_STRATEGY_ID = 'technical_backtest_strategy_id';

function saveState<T>(key: string, data: T): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(data));
  } catch {
    // 静默降级：quota 满或隐私模式下不影响功能
  }
}

function loadState<T>(key: string, validate?: (v: unknown) => boolean): T | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (validate && !validate(parsed)) return null;
    return parsed as T;
  } catch {
    return null;
  }
}

/** 运行时校验：确保值为非空数组 */
function isNonEmptyArray(v: unknown): v is unknown[] {
  return Array.isArray(v) && v.length > 0;
}

function clearState(key: string): void {
  try {
    sessionStorage.removeItem(key);
  } catch {
    // 静默降级
  }
}

interface UseTechnicalBacktestOptions {
  technicalCodes: string;
  technicalStartDate: string;
  technicalEndDate: string;
  technicalEvalDays: string;
}

interface UseTechnicalBacktestReturn {
  // 策略
  strategies: StrategyConfig[];
  selectedStrategyId: string;
  setSelectedStrategyId: (id: string) => void;
  selectedStrategy: StrategyConfig | undefined;
  strategyError: ParsedApiError | null;

  // 参数组
  paramGroups: ParamGroup[];
  invalidGroupIds: Set<string>;
  addParamGroup: () => void;
  removeParamGroup: (id: string) => void;
  duplicateParamGroup: (id: string) => void;
  updateParamValue: (groupId: string, key: string, value: number | boolean) => void;
  updateGroupName: (groupId: string, name: string) => void;
  toggleGroupEnabled: (groupId: string) => void;
  setInvalidGroupIds: (ids: Set<string>) => void;

  // 回测结果
  batchResults: ParamGroupResult[] | null;
  isBatchRunning: boolean;
  technicalError: ParsedApiError | null;
  setTechnicalError: (err: ParsedApiError | null) => void;
  handleRunBatch: () => Promise<void>;

  // 参数组模板
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
  const { technicalCodes, technicalStartDate, technicalEndDate, technicalEvalDays } = options;

  // 策略列表
  const [strategies, setStrategies] = useState<StrategyConfig[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState('');
  const [strategyError, setStrategyError] = useState<ParsedApiError | null>(null);

  // 参数组
  const [paramGroups, setParamGroups] = useState<ParamGroup[]>([]);
  const [invalidGroupIds, setInvalidGroupIds] = useState<Set<string>>(new Set());

  // 回测结果
  const [batchResults, setBatchResults] = useState<ParamGroupResult[] | null>(null);
  const [isBatchRunning, setIsBatchRunning] = useState(false);
  const [technicalError, setTechnicalError] = useState<ParsedApiError | null>(null);

  // 模板
  const [templates, setTemplates] = useState<BacktestTemplateItem[]>([]);
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false);

  // 页面刷新后恢复 sessionStorage 中的结果和参数
  useEffect(() => {
    const savedResults = loadState<ParamGroupResult[]>(STORAGE_KEY_RESULTS, isNonEmptyArray);
    const savedParamGroups = loadState<ParamGroup[]>(STORAGE_KEY_PARAM_GROUPS, isNonEmptyArray);
    const savedStrategyId = loadState<string>(STORAGE_KEY_STRATEGY_ID);

    if (savedResults) setBatchResults(savedResults);
    if (savedParamGroups && savedParamGroups.length > 0) setParamGroups(savedParamGroups);
    if (savedStrategyId) setSelectedStrategyId(savedStrategyId);
  }, []);

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
      saveState(STORAGE_KEY_RESULTS, batchResults);
    }
  }, [batchResults]);

  // 参数组变化时持久化到 sessionStorage
  useEffect(() => {
    saveState(STORAGE_KEY_PARAM_GROUPS, paramGroups);
  }, [paramGroups]);

  // 策略切换时持久化策略 ID
  useEffect(() => {
    if (selectedStrategyId) {
      saveState(STORAGE_KEY_STRATEGY_ID, selectedStrategyId);
    }
  }, [selectedStrategyId]);

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
      setParamGroups([
        {
          id: crypto.randomUUID(),
          name: '参数组 1',
          enabled: true,
          params: buildDefaultParams(strategy.parameters),
        },
      ]);
      setBatchResults(null);
      clearState(STORAGE_KEY_RESULTS);
    } else if (paramGroups.length === 0) {
      // 首次加载且无 sessionStorage 恢复数据时，初始化默认参数组
      setParamGroups([
        {
          id: crypto.randomUUID(),
          name: '参数组 1',
          enabled: true,
          params: buildDefaultParams(strategy.parameters),
        },
      ]);
    } else {
      // sessionStorage 恢复了参数组，校验参数键是否与当前策略一致
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

  // 策略切换时自动加载模板列表
  useEffect(() => {
    if (!selectedStrategyId) return;
    setIsLoadingTemplates(true);
    backtestApi.listTemplates(selectedStrategyId)
      .then(setTemplates)
      .catch(() => setTemplates([]))
      .finally(() => setIsLoadingTemplates(false));
  }, [selectedStrategyId]);

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
  }, [selectedStrategy, paramGroups.length]);

  const removeParamGroup = useCallback((id: string) => {
    setParamGroups((prev) => prev.filter((g) => g.id !== id));
  }, []);

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
  }, [selectedStrategy, paramGroups]);

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
  }, []);

  const updateGroupName = useCallback((groupId: string, name: string) => {
    setParamGroups((prev) =>
      prev.map((g) => (g.id === groupId ? { ...g, name } : g)),
    );
  }, []);

  const toggleGroupEnabled = useCallback((groupId: string) => {
    setParamGroups((prev) =>
      prev.map((g) =>
        g.id === groupId ? { ...g, enabled: !g.enabled } : g,
      ),
    );
  }, []);

  const loadTemplates = useCallback(async () => {
    if (!selectedStrategyId) return;
    setIsLoadingTemplates(true);
    try {
      const items = await backtestApi.listTemplates(selectedStrategyId);
      setTemplates(items);
    } catch {
      setTemplates([]);
    } finally {
      setIsLoadingTemplates(false);
    }
  }, [selectedStrategyId]);

  const saveAsTemplate = useCallback(async (name: string) => {
    if (!selectedStrategyId || !name.trim()) return;
    try {
      await backtestApi.saveTemplate({
        strategyId: selectedStrategyId,
        name: name.trim(),
        params: paramGroups,
      });
      await loadTemplates();
    } catch (err) {
      setTechnicalError(getParsedApiError(err));
    }
  }, [selectedStrategyId, paramGroups, loadTemplates]);

  const deleteTemplate = useCallback(async (id: number) => {
    const previous = templates;
    setTemplates((prev) => prev.filter((t) => t.id !== id));
    try {
      await backtestApi.deleteTemplate(id);
    } catch (err) {
      setTemplates(previous); // 回滚乐观删除
      setTechnicalError(getParsedApiError(err));
    }
  }, [templates]);

  const loadTemplate = useCallback((template: BacktestTemplateItem) => {
    if (template.params.length === 0) return;
    setParamGroups(template.params);
    setBatchResults(null);
    clearState(STORAGE_KEY_RESULTS);
  }, []);

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
    if (!technicalStartDate || !technicalEndDate) return;

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

    setIsBatchRunning(true);
    setBatchResults(null);
    setTechnicalError(null);
    try {
      const results = await backtestApi.runTechnicalBatch({
        codes,
        startDate: technicalStartDate,
        endDate: technicalEndDate,
        evalWindowDays: parseInt(technicalEvalDays, 10) || 10,
        strategyId: selectedStrategyId,
        paramGroups: enabledGroups,
      });
      setBatchResults(results);
    } catch (err) {
      setTechnicalError(getParsedApiError(err));
    } finally {
      setIsBatchRunning(false);
    }
  }, [technicalCodes, technicalStartDate, technicalEndDate, technicalEvalDays, paramGroups, invalidGroupIds, selectedStrategyId]);

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
