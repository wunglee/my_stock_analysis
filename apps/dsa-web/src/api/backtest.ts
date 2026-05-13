import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  BacktestRunRequest,
  BacktestRunResponse,
  BacktestResultsResponse,
  BacktestResultItem,
  PerformanceMetrics,
} from '../types/backtest';
import type {
  TechnicalBacktestResult,
  StrategyConfig,
  ParamGroup,
  ParamGroupResult,
  BacktestTemplateItem,
  BacktestSession,
} from '../types/technicalBacktest';
// 所有 mock 数据已从后端 API 获取，前端不再维护本地 mock
// 如需查看旧的前端 mock 实现，参见 git 历史中的 src/api/mock/backtestMock.ts

// ============ API ============

export const backtestApi = {
  /**
   * Trigger backtest evaluation
   */
  run: async (params: BacktestRunRequest = {}): Promise<BacktestRunResponse> => {
    const requestData: Record<string, unknown> = {};
    if (params.code) requestData.code = params.code;
    if (params.force) requestData.force = params.force;
    if (params.evalWindowDays) requestData.eval_window_days = params.evalWindowDays;
    if (params.minAgeDays != null) requestData.min_age_days = params.minAgeDays;
    if (params.limit) requestData.limit = params.limit;

    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/backtest/run',
      requestData,
    );
    return toCamelCase<BacktestRunResponse>(response.data);
  },

  /**
   * Get paginated backtest results
   */
  getResults: async (params: {
    code?: string;
    evalWindowDays?: number;
    analysisDateFrom?: string;
    analysisDateTo?: string;
    page?: number;
    limit?: number;
  } = {}): Promise<BacktestResultsResponse> => {
    const { code, evalWindowDays, analysisDateFrom, analysisDateTo, page = 1, limit = 20 } = params;

    const queryParams: Record<string, string | number> = { page, limit };
    if (code) queryParams.code = code;
    if (evalWindowDays) queryParams.eval_window_days = evalWindowDays;
    if (analysisDateFrom) queryParams.analysis_date_from = analysisDateFrom;
    if (analysisDateTo) queryParams.analysis_date_to = analysisDateTo;

    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/backtest/results',
      { params: queryParams },
    );

    const data = toCamelCase<BacktestResultsResponse>(response.data);
    return {
      total: data.total,
      page: data.page,
      limit: data.limit,
      items: (data.items || []).map(item => toCamelCase<BacktestResultItem>(item)),
    };
  },

  /**
   * Get overall performance metrics
   */
  getOverallPerformance: async (params: {
    evalWindowDays?: number;
    analysisDateFrom?: string;
    analysisDateTo?: string;
  } = {}): Promise<PerformanceMetrics | null> => {
    try {
      const queryParams: Record<string, string | number> = {};
      if (params.evalWindowDays) queryParams.eval_window_days = params.evalWindowDays;
      if (params.analysisDateFrom) queryParams.analysis_date_from = params.analysisDateFrom;
      if (params.analysisDateTo) queryParams.analysis_date_to = params.analysisDateTo;
      const response = await apiClient.get<Record<string, unknown>>(
        '/api/v1/backtest/performance',
        { params: queryParams },
      );
      return toCamelCase<PerformanceMetrics>(response.data);
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { status?: number } };
        if (axiosErr.response?.status === 404) return null;
      }
      throw err;
    }
  },

  /**
   * Get per-stock performance metrics
   */
  getStockPerformance: async (code: string, params: {
    evalWindowDays?: number;
    analysisDateFrom?: string;
    analysisDateTo?: string;
  } = {}): Promise<PerformanceMetrics | null> => {
    try {
      const queryParams: Record<string, string | number> = {};
      if (params.evalWindowDays) queryParams.eval_window_days = params.evalWindowDays;
      if (params.analysisDateFrom) queryParams.analysis_date_from = params.analysisDateFrom;
      if (params.analysisDateTo) queryParams.analysis_date_to = params.analysisDateTo;
      const response = await apiClient.get<Record<string, unknown>>(
        `/api/v1/backtest/performance/${encodeURIComponent(code)}`,
        { params: queryParams },
      );
      return toCamelCase<PerformanceMetrics>(response.data);
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { status?: number } };
        if (axiosErr.response?.status === 404) return null;
      }
      throw err;
    }
  },

  /**
   * Run pure technical backtest (no AI)
   */
  runTechnical: async (params: {
    codes: string[];
    startDate?: string;
    endDate?: string;
    evalWindowDays?: number;
  }): Promise<TechnicalBacktestResult> => {
    const requestData: Record<string, unknown> = {
      codes: params.codes,
      eval_window_days: params.evalWindowDays ?? 10,
    };
    if (params.startDate) requestData.start_date = params.startDate;
    if (params.endDate) requestData.end_date = params.endDate;
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/backtest/technical',
      requestData,
    );
    return toCamelCase<TechnicalBacktestResult>(response.data);
  },

  // ============ v2.0: 策略配置 + 参数组回测（数据全部来自后端）============

  /**
   * 获取策略列表
   * GET /api/v1/backtest/strategies
   */
  getStrategies: async (): Promise<StrategyConfig[]> => {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/backtest/strategies',
    );
    const data = toCamelCase<{ strategies?: StrategyConfig[] }>(response.data);
    // toCamelCase 只转换对象键名，不转换字符串值。策略参数的 key
    // 和校验规则的 paramA/paramB 是 snake_case 字符串值（如 "short_period"），
    // 需手动转为 camelCase 才能与 group.params 的键名匹配。
    const toCamel = (s: string) => s.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());
    for (const s of data.strategies || []) {
      for (const p of s.parameters) {
        p.key = toCamel(p.key);
      }
      for (const r of s.validationRules) {
        if (r.paramA) r.paramA = toCamel(r.paramA);
        if (r.paramB) r.paramB = toCamel(r.paramB);
      }
    }
    return data.strategies || [];
  },

  /**
   * 带参数组的批量回测
   * POST /api/v1/backtest/technical/batch
   *
   * 后端完成全部计算：信号调整、收益率曲线、交易明细
   */
  runTechnicalBatch: async (params: {
    codes: string[];
    startDate: string;
    endDate: string;
    evalWindowDays: number;
    strategyId: string;
    paramGroups: Array<{
      id: string;
      name: string;
      params: Record<string, number | boolean>;
    }>;
  }): Promise<ParamGroupResult[]> => {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/backtest/technical/batch',
      {
        codes: params.codes,
        start_date: params.startDate,
        end_date: params.endDate,
        eval_window_days: params.evalWindowDays,
        strategy_id: params.strategyId,
        param_groups: params.paramGroups.map((g) => ({
          id: g.id,
          name: g.name,
          params: g.params,
        })),
      },
    );

    const data = toCamelCase<{ results?: ParamGroupResult[] }>(response.data);
    return data.results || [];
  },

  // ============ P3: 参数组模板 CRUD ============

  /**
   * 获取指定策略的模板列表
   * GET /api/v1/backtest/technical/templates?strategy_id=X
   */
  listTemplates: async (strategyId: string): Promise<BacktestTemplateItem[]> => {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/backtest/technical/templates',
      { params: { strategy_id: strategyId } },
    );
    const data = toCamelCase<{ templates?: BacktestTemplateItem[] }>(response.data);
    return data.templates || [];
  },

  /**
   * 保存参数组模板
   * POST /api/v1/backtest/technical/templates
   */
  saveTemplate: async (data: {
    strategyId: string;
    name: string;
    params: ParamGroup[];
  }): Promise<BacktestTemplateItem> => {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/backtest/technical/templates',
      {
        strategy_id: data.strategyId,
        name: data.name,
        params: data.params.map((g) => ({
          id: g.id,
          name: g.name,
          enabled: g.enabled,
          params: g.params,
        })),
      },
    );
    return toCamelCase<BacktestTemplateItem>(response.data);
  },

  /**
   * 删除参数组模板
   * DELETE /api/v1/backtest/technical/templates/{id}
   */
  deleteTemplate: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/v1/backtest/technical/templates/${id}`);
  },

  // ============ P4: 自动持久化会话 ============

  /**
   * 加载回测会话
   * GET /api/v1/backtest/technical/session?stock_code=X&strategy_id=Y
   * 返回 null 表示 404（无会话数据）
   */
  loadSession: async (stockCode: string, strategyId: string): Promise<BacktestSession | null> => {
    try {
      const response = await apiClient.get<Record<string, unknown>>(
        '/api/v1/backtest/technical/session',
        { params: { stock_code: stockCode, strategy_id: strategyId } },
      );
      return toCamelCase<BacktestSession>(response.data);
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { status?: number } };
        if (axiosErr.response?.status === 404) return null;
      }
      throw err;
    }
  },

  /**
   * 保存回测会话 (upsert)
   * POST /api/v1/backtest/technical/session
   */
  saveSession: async (data: {
    stockCode: string;
    strategyId: string;
    paramGroups: ParamGroup[];
    batchResults?: ParamGroupResult[] | null;
  }): Promise<BacktestSession> => {
    const body: Record<string, unknown> = {
      stock_code: data.stockCode,
      strategy_id: data.strategyId,
      param_groups: data.paramGroups.map((g) => ({
        id: g.id,
        name: g.name,
        enabled: g.enabled,
        params: g.params,
      })),
    };
    if (data.batchResults !== undefined) {
      body.batch_results = data.batchResults;
    }
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/backtest/technical/session',
      body,
    );
    return toCamelCase<BacktestSession>(response.data);
  },
};
