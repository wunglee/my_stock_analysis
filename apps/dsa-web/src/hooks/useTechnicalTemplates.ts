import { useState, useEffect, useCallback, useRef } from 'react';
import { backtestApi } from '../api/backtest';
import { getParsedApiError } from '../api/error';
import type { ParsedApiError } from '../api/error';
import type { BacktestTemplateItem, ParamGroup } from '../types/technicalBacktest';

const STORAGE_KEY_RESULTS = 'technical_backtest_results';

export interface UseTechnicalTemplatesOptions {
  selectedStrategyId: string;
  paramGroups: ParamGroup[];
}

export interface UseTechnicalTemplatesReturn {
  templates: BacktestTemplateItem[];
  isLoadingTemplates: boolean;
  loadTemplates: () => Promise<void>;
  saveAsTemplate: (name: string) => Promise<void>;
  deleteTemplate: (id: number) => Promise<void>;
  loadTemplate: (template: BacktestTemplateItem) => void;
}

/**
 * 参数组模板 CRUD Hook。
 * 从 useTechnicalBacktest 中提取，单一职责：模板的增删改查。
 *
 * 调用方需要传入 setParamGroups 和 setBatchResults 来响应模板加载。
 */
export function useTechnicalTemplates(
  options: UseTechnicalTemplatesOptions,
  setParamGroups: (groups: ParamGroup[]) => void,
  setBatchResults: (results: null) => void,
  setTechnicalError: (err: ParsedApiError | null) => void,
): UseTechnicalTemplatesReturn {
  const { selectedStrategyId, paramGroups } = options;

  const [templates, setTemplates] = useState<BacktestTemplateItem[]>([]);
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false);
  const mountedRef = useRef(false);

  const loadTemplates = useCallback(async () => {
    if (!selectedStrategyId) return;
    setIsLoadingTemplates(true);
    try {
      const items = await backtestApi.listTemplates(selectedStrategyId);
      if (mountedRef.current) setTemplates(items);
    } catch {
      if (mountedRef.current) setTemplates([]);
    } finally {
      if (mountedRef.current) setIsLoadingTemplates(false);
    }
  }, [selectedStrategyId]);

  // 策略切换时自动加载模板列表
  useEffect(() => {
    mountedRef.current = true;
    if (!selectedStrategyId) return;
    setIsLoadingTemplates(true);
    backtestApi.listTemplates(selectedStrategyId)
      .then((items) => { if (mountedRef.current) setTemplates(items); })
      .catch(() => { if (mountedRef.current) setTemplates([]); })
      .finally(() => { if (mountedRef.current) setIsLoadingTemplates(false); });
    return () => { mountedRef.current = false; };
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
  }, [selectedStrategyId, paramGroups, loadTemplates, setTechnicalError]);

  const deleteTemplate = useCallback(async (id: number) => {
    const previous = templates;
    setTemplates((prev) => prev.filter((t) => t.id !== id));
    try {
      await backtestApi.deleteTemplate(id);
    } catch (err) {
      setTemplates(previous);
      setTechnicalError(getParsedApiError(err));
    }
  }, [templates, setTechnicalError]);

  const loadTemplate = useCallback((template: BacktestTemplateItem) => {
    if (template.params.length === 0) return;
    setParamGroups(template.params);
    setBatchResults(null);
    try { sessionStorage.removeItem(STORAGE_KEY_RESULTS); } catch { /* 静默降级 */ }
  }, [setParamGroups, setBatchResults]);

  return {
    templates,
    isLoadingTemplates,
    loadTemplates,
    saveAsTemplate,
    deleteTemplate,
    loadTemplate,
  };
}
