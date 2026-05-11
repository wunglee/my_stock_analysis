import type React from 'react';
import { useState, useEffect, useCallback, useMemo } from 'react';
import { Check, Minus, X } from 'lucide-react';
import { StockAutocomplete } from '../components/StockAutocomplete';
import { ParamGroupEditor } from '../components/backtest/ParamGroupEditor';
import { TemplateManager } from '../components/backtest/TemplateManager';
import { ParamGroupResultRow } from '../components/backtest/ParamGroupResultRow';
import { backtestApi } from '../api/backtest';
import type { ParsedApiError } from '../api/error';
import { getParsedApiError } from '../api/error';
import { ApiErrorAlert, Card, Badge, EmptyState, Pagination, StatusDot, Tooltip } from '../components/common';
import type {
  BacktestResultItem,
  BacktestRunResponse,
  PerformanceMetrics,
} from '../types/backtest';
import { useTechnicalBacktest } from '../hooks/useTechnicalBacktest';
import { useKlineOverlay } from '../hooks/useKlineOverlay';

const BACKTEST_COMPACT_INPUT_CLASS =
  'input-surface input-focus-glow h-10 rounded-xl border bg-transparent px-3 py-2 text-xs transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60';

// ============ Helpers ============

function pct(value?: number | null): string {
  if (value == null) return '--';
  return `${value.toFixed(1)}%`;
}

function outcomeBadge(outcome?: string) {
  if (!outcome) return <Badge variant="default">--</Badge>;
  switch (outcome) {
    case 'win':
      return <Badge variant="success" glow>赢</Badge>;
    case 'loss':
      return <Badge variant="danger" glow>输</Badge>;
    case 'neutral':
      return <Badge variant="warning">平</Badge>;
    default:
      return <Badge variant="default">{outcome}</Badge>;
  }
}

function statusBadge(status: string) {
  switch (status) {
    case 'completed':
      return <Badge variant="success">已完成</Badge>;
    case 'insufficient':
    case 'insufficient_data':
      return <Badge variant="warning">数据不足</Badge>;
    case 'error':
      return <Badge variant="danger">错误</Badge>;
    default:
      return <Badge variant="default">{status}</Badge>;
  }
}

function actualMovementBadge(movement?: string | null) {
  switch (movement) {
    case 'up':
      return <Badge variant="success">涨</Badge>;
    case 'down':
      return <Badge variant="danger">跌</Badge>;
    case 'flat':
      return <Badge variant="warning">平</Badge>;
    default:
      return <Badge variant="default">--</Badge>;
  }
}

function boolIcon(value?: boolean | null) {
  if (value === true) {
    return (
      <span
        className="backtest-status-chip backtest-status-chip-success"
        aria-label="是"
      >
        <StatusDot tone="success" className="backtest-status-chip-dot" />
        <Check className="h-3.5 w-3.5" />
      </span>
    );
  }

  if (value === false) {
    return (
      <span
        className="backtest-status-chip backtest-status-chip-danger"
        aria-label="否"
      >
        <StatusDot tone="danger" className="backtest-status-chip-dot" />
        <X className="h-3.5 w-3.5" />
      </span>
    );
  }

  return (
    <span
      className="backtest-status-chip backtest-status-chip-neutral"
      aria-label="未知"
    >
      <StatusDot tone="neutral" className="backtest-status-chip-dot" />
      <Minus className="h-3.5 w-3.5" />
    </span>
  );
}

// ============ Metric Row ============

const MetricRow: React.FC<{ label: string; value: string; accent?: boolean }> = ({ label, value, accent }) => (
  <div className="backtest-metric-row">
    <span className="label">{label}</span>
    <span className={`value ${accent ? 'accent' : ''}`}>{value}</span>
  </div>
);

// ============ Performance Card ============

const PerformanceCard: React.FC<{ metrics: PerformanceMetrics; title: string }> = ({ metrics, title }) => (
  <Card variant="gradient" padding="md" className="animate-fade-in">
    <div className="mb-3">
      <span className="label-uppercase">{title}</span>
    </div>
    <MetricRow label="方向准确率" value={pct(metrics.directionAccuracyPct)} accent />
    <MetricRow label="胜率" value={pct(metrics.winRatePct)} accent />
    <MetricRow label="平均模拟收益" value={pct(metrics.avgSimulatedReturnPct)} />
    <MetricRow label="平均股票收益" value={pct(metrics.avgStockReturnPct)} />
    <MetricRow label="止损触发率" value={pct(metrics.stopLossTriggerRate)} />
    <MetricRow label="止盈触发率" value={pct(metrics.takeProfitTriggerRate)} />
    <MetricRow label="平均触及天数" value={metrics.avgDaysToFirstHit != null ? metrics.avgDaysToFirstHit.toFixed(1) : '--'} />
    <div className="backtest-metric-footer">
      <span className="text-xs text-muted-text">评估数</span>
      <span className="text-xs text-secondary-text font-mono">
        {Number(metrics.completedCount)} / {Number(metrics.totalEvaluations)}
      </span>
    </div>
    <div className="flex items-center justify-between">
      <span className="text-xs text-muted-text">赢/输/平</span>
      <span className="text-xs font-mono">
        <span className="text-success">{metrics.winCount}</span>
        {' / '}
        <span className="text-danger">{metrics.lossCount}</span>
        {' / '}
        <span className="text-warning">{metrics.neutralCount}</span>
      </span>
    </div>
  </Card>
);

// ============ Run Summary ============

const RunSummary: React.FC<{ data: BacktestRunResponse }> = ({ data }) => (
  <div className="backtest-summary animate-fade-in">
    <span className="label">已处理: <span className="value">{data.processed}</span></span>
    <span className="label">已保存: <span className="value primary">{data.saved}</span></span>
    <span className="label">已完成: <span className="value success">{data.completed}</span></span>
    <span className="label">数据不足: <span className="value warning">{data.insufficient}</span></span>
    {data.errors > 0 && (
      <span className="label">错误: <span className="value danger">{data.errors}</span></span>
    )}
  </div>
);

// ============ Main Page ============

const BacktestPage: React.FC = () => {
  // Set page title
  useEffect(() => {
    document.title = '策略回测 - DSA';
  }, []);

  // 默认日期范围：一年前至今
  const today = new Date();
  const oneYearAgo = new Date(today);
  oneYearAgo.setFullYear(today.getFullYear() - 1);
  const fmt = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const defaultEndDate = fmt(today);
  const defaultStartDate = fmt(oneYearAgo);

  // Input state
  const [codeFilter, setCodeFilter] = useState('');
  const [analysisDateFrom, setAnalysisDateFrom] = useState(defaultStartDate);
  const [analysisDateTo, setAnalysisDateTo] = useState(defaultEndDate);
  const [evalDays, setEvalDays] = useState('');
  const [forceRerun, setForceRerun] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [runResult, setRunResult] = useState<BacktestRunResponse | null>(null);
  const [runError, setRunError] = useState<ParsedApiError | null>(null);
  const [pageError, setPageError] = useState<ParsedApiError | null>(null);

  // Results state
  const [results, setResults] = useState<BacktestResultItem[]>([]);
  const [totalResults, setTotalResults] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [isLoadingResults, setIsLoadingResults] = useState(false);
  const pageSize = 20;

  // Performance state
  const [overallPerf, setOverallPerf] = useState<PerformanceMetrics | null>(null);
  const [stockPerf, setStockPerf] = useState<PerformanceMetrics | null>(null);
  const [isLoadingPerf, setIsLoadingPerf] = useState(false);
  const effectiveWindowDays = evalDays ? parseInt(evalDays, 10) : overallPerf?.evalWindowDays;
  const isNextDayValidation = effectiveWindowDays === 1;
  const showNextDayActualColumns = isNextDayValidation;

  // Technical backtest state
  const [isTechnicalMode, setIsTechnicalMode] = useState(false);
  const [technicalCodes, setTechnicalCodes] = useState('');
  const [technicalStartDate, setTechnicalStartDate] = useState(defaultStartDate);
  const [technicalEndDate, setTechnicalEndDate] = useState(defaultEndDate);
  const [technicalEvalDays, setTechnicalEvalDays] = useState('10');
  const [klineLoaded, setKlineLoaded] = useState(false);

  // 加载 K 线图（window.KlineChart 在 index.html 中通过 <script> 加载）
  const doLoadKline = useCallback((codes: string) => {
    const tokens = codes.split(/[,，\s]+/).filter(Boolean);
    if (tokens.length === 0) return;

    const code = tokens[0].trim();
    const pureCode = code.replace(/\.(SH|SZ|HK|US)$/i, '');
    setKlineLoaded(true);

    requestAnimationFrame(() => {
      window.KlineChart?.setCurrent({ id: pureCode }, 'CN', false);
      window.KlineChart?.setRealtimeUpdateEnabled(false);
    });
  }, []);

  const handleLoadKline = useCallback(() => {
    doLoadKline(technicalCodes);
  }, [technicalCodes, doLoadKline]);

  // 切换模式时停止K线实时更新并重置加载状态
  const handleModeSwitch = useCallback((technical: boolean) => {
    if (!technical) {
      window.KlineChart?.stopRealtimeKlineUpdateTimer();
      setKlineLoaded(false);
    }
    setIsTechnicalMode(technical);
  }, []);

  // v2.0: 策略与参数组逻辑封装到 hook
  const {
    strategies,
    selectedStrategyId,
    setSelectedStrategyId,
    selectedStrategy,
    strategyError,
    paramGroups,
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
    handleRunBatch,
    templates,
    isLoadingTemplates,
    saveAsTemplate,
    deleteTemplate,
    loadTemplate,
  } = useTechnicalBacktest({
    technicalCodes,
    technicalStartDate,
    technicalEndDate,
    technicalEvalDays,
  });

  // K线图 Overlay 管理
  const {
    activeGroupId,
    setActiveGroupId,
    shouldHideBuiltinMA,
    setShouldHideBuiltinMA,
  } = useKlineOverlay({
    chartReady: klineLoaded,
    paramGroups,
    strategy: selectedStrategy,
  });

  // 从多代码输入中提取最后一个 token 作为搜索关键词
  // 如果最后一个 token 已经是完整代码（带市场后缀），则不触发搜索
  const technicalSearchQuery = useMemo(() => {
    const tokens = technicalCodes.split(/[,，\s]+/).filter(Boolean);
    if (tokens.length <= 1) return technicalCodes;
    const last = tokens[tokens.length - 1];
    if (/^\d{5,6}\.[A-Z]{2}$/i.test(last)) return '';
    return last;
  }, [technicalCodes]);

  // Fetch results
  const fetchResults = useCallback(async (
    page = 1,
    code?: string,
    windowDays?: number,
    startDate?: string,
    endDate?: string,
  ) => {
    setIsLoadingResults(true);
    try {
      const response = await backtestApi.getResults({
        code: code || undefined,
        evalWindowDays: windowDays,
        analysisDateFrom: startDate || undefined,
        analysisDateTo: endDate || undefined,
        page,
        limit: pageSize,
      });
      setResults(response.items);
      setTotalResults(response.total);
      setCurrentPage(response.page);
      setPageError(null);
    } catch (err) {
      // 错误已通过 setPageError 传递给 UI 展示
      setPageError(getParsedApiError(err));
    } finally {
      setIsLoadingResults(false);
    }
  }, []);

  // Fetch performance
  const fetchPerformance = useCallback(async (
    code?: string,
    windowDays?: number,
    startDate?: string,
    endDate?: string,
  ) => {
    setIsLoadingPerf(true);
    try {
      const overall = await backtestApi.getOverallPerformance({
        evalWindowDays: windowDays,
        analysisDateFrom: startDate || undefined,
        analysisDateTo: endDate || undefined,
      });
      setOverallPerf(overall);

      if (code) {
        const stock = await backtestApi.getStockPerformance(code, {
          evalWindowDays: windowDays,
          analysisDateFrom: startDate || undefined,
          analysisDateTo: endDate || undefined,
        });
        setStockPerf(stock);
      } else {
        setStockPerf(null);
      }
      setPageError(null);
    } catch (err) {
      // 错误已通过 setPageError 传递给 UI 展示
      setPageError(getParsedApiError(err));
    } finally {
      setIsLoadingPerf(false);
    }
  }, []);

  // Initial load — fetch performance first, then filter results by its window
  useEffect(() => {
    const init = async () => {
      // Get latest performance (unfiltered returns most recent summary)
      const overall = await backtestApi.getOverallPerformance();
      setOverallPerf(overall);
      // Use the summary's eval_window_days to filter results consistently
      const windowDays = overall?.evalWindowDays;
      if (windowDays && !evalDays) {
        setEvalDays(String(windowDays));
      }
      fetchResults(1, undefined, windowDays, undefined, undefined);
    };
    init();
  }, [fetchResults]);

  // Run backtest
  const handleRun = async () => {
    setIsRunning(true);
    setRunResult(null);
    setRunError(null);
    try {
      const code = codeFilter.trim() || undefined;
      const evalWindowDays = evalDays ? parseInt(evalDays, 10) : undefined;
      const response = await backtestApi.run({
        code,
        force: forceRerun || undefined,
        minAgeDays: forceRerun ? 0 : undefined,
        evalWindowDays,
      });
      setRunResult(response);
      // Refresh data with same eval_window_days
      fetchResults(1, codeFilter.trim() || undefined, evalWindowDays, analysisDateFrom, analysisDateTo);
      fetchPerformance(codeFilter.trim() || undefined, evalWindowDays, analysisDateFrom, analysisDateTo);
    } catch (err) {
      setRunError(getParsedApiError(err));
    } finally {
      setIsRunning(false);
    }
  };

  // Filter by code
  const handleFilter = () => {
    const code = codeFilter.trim() || undefined;
    const windowDays = evalDays ? parseInt(evalDays, 10) : undefined;
    setCurrentPage(1);
    fetchResults(1, code, windowDays, analysisDateFrom, analysisDateTo);
    fetchPerformance(code, windowDays, analysisDateFrom, analysisDateTo);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleFilter();
    }
  };

  const handleShowNextDay = () => {
    const code = codeFilter.trim() || undefined;
    setEvalDays('1');
    setCurrentPage(1);
    fetchResults(1, code, 1, analysisDateFrom, analysisDateTo);
    fetchPerformance(code, 1, analysisDateFrom, analysisDateTo);
  };

  // Pagination
  const totalPages = Math.ceil(totalResults / pageSize);
  const handlePageChange = (page: number) => {
    const windowDays = evalDays ? parseInt(evalDays, 10) : undefined;
    fetchResults(page, codeFilter.trim() || undefined, windowDays, analysisDateFrom, analysisDateTo);
  };

  return (
    <div className="min-h-full flex flex-col rounded-[1.5rem] bg-transparent">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-white/5 px-3 py-3 sm:px-4">
        {/* Mode Toggle */}
        <div className="flex items-center gap-1 mb-3">
          <button
            type="button"
            onClick={() => handleModeSwitch(false)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              !isTechnicalMode
                ? 'bg-accent text-accent-foreground'
                : 'text-muted-text hover:text-foreground hover:bg-white/5'
            }`}
          >
            AI 回测
          </button>
          <button
            type="button"
            onClick={() => handleModeSwitch(true)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              isTechnicalMode
                ? 'bg-accent text-accent-foreground'
                : 'text-muted-text hover:text-foreground hover:bg-white/5'
            }`}
          >
            纯技术回测
          </button>
        </div>

        {isTechnicalMode ? (
          <>
          {/* v2.0 Technical Mode Controls */}
          {/* Row 1: Stock + Dates + Load Kline（始终可见） */}
          <div className="flex max-w-5xl flex-wrap items-center gap-2 mb-3">
            <div className="relative min-w-0 flex-[1_1_220px]">
              <StockAutocomplete
                value={technicalCodes}
                onChange={setTechnicalCodes}
                searchQuery={technicalSearchQuery}
                submitOnSelect={false}
                onSubmit={(code, _name, _source) => {
                  // 二次回车确认 → 触发 K 线加载
                  // 选中下拉项时仅更新输入框（通过 onChange），不触发此回调
                  const codes = code.trim();
                  if (codes) {
                    setTechnicalCodes(codes);
                    doLoadKline(codes);
                  }
                }}
                placeholder="输入股票代码，逗号分隔（如：600519,000858）"
                disabled={isBatchRunning}
              />
            </div>
            <div className="flex items-center gap-2 whitespace-nowrap">
              <span className="text-xs text-muted-text">从</span>
              <input
                type="date"
                aria-label="开始日期"
                value={technicalStartDate}
                onChange={(e) => setTechnicalStartDate(e.target.value)}
                className={`${BACKTEST_COMPACT_INPUT_CLASS} w-40 text-center tabular-nums`}
              />
            </div>
            <div className="flex items-center gap-2 whitespace-nowrap">
              <span className="text-xs text-muted-text">到</span>
              <input
                type="date"
                aria-label="结束日期"
                value={technicalEndDate}
                onChange={(e) => setTechnicalEndDate(e.target.value)}
                className={`${BACKTEST_COMPACT_INPUT_CLASS} w-40 text-center tabular-nums`}
              />
            </div>
            <div className="flex items-center gap-2 whitespace-nowrap">
              <span className="text-xs text-muted-text">窗口</span>
              <input
                type="number"
                min={1}
                max={120}
                value={technicalEvalDays}
                onChange={(e) => setTechnicalEvalDays(e.target.value)}
                placeholder="10"
                className={`${BACKTEST_COMPACT_INPUT_CLASS} w-20 text-center tabular-nums`}
              />
            </div>
            <button
              type="button"
              onClick={handleLoadKline}
              disabled={!technicalCodes.trim() || isBatchRunning}
              className="btn-secondary flex items-center gap-1.5 whitespace-nowrap"
            >
              加载K线
            </button>
          </div>

          {/* K线加载后：K线图 + 回测参数面板 */}
          {klineLoaded && (
            <>
              {/* K线图容器（window.KlineChart 直接操作此 DOM） */}
              <div className="max-w-5xl mb-3">
                <div
                  id="klineContainer"
                  style={{ width: '100%', minHeight: 900 }}
                />
              </div>

              {/* 回测参数面板：策略 + 模板 + 参数组 + 运行 */}
              <Card variant="gradient" padding="md" className="max-w-5xl mb-3 animate-fade-in">
                {/* 策略选择 + 运行按钮 */}
                <div className="flex flex-wrap items-center gap-2 mb-3">
                  <div className="flex items-center gap-2 whitespace-nowrap">
                    <span className="text-xs text-muted-text">策略</span>
                    <select
                      value={selectedStrategyId}
                      onChange={(e) => setSelectedStrategyId(e.target.value)}
                      disabled={isBatchRunning}
                      className={`${BACKTEST_COMPACT_INPUT_CLASS} w-40 cursor-pointer`}
                    >
                      {strategies.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button
                    type="button"
                    onClick={handleRunBatch}
                    disabled={isBatchRunning || !selectedStrategyId}
                    className="btn-primary flex items-center gap-1.5 whitespace-nowrap"
                  >
                    {isBatchRunning ? (
                      <>
                        <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        回测中...
                      </>
                    ) : (
                      '运行批量回测'
                    )}
                  </button>
                </div>

                {/* 图表显示选项 */}
                <div className="flex items-center gap-3 mb-3">
                  <label className="flex items-center gap-2 cursor-pointer text-xs text-secondary-text hover:text-foreground transition-colors">
                    <input
                      type="checkbox"
                      checked={shouldHideBuiltinMA}
                      onChange={(e) => setShouldHideBuiltinMA(e.target.checked)}
                      className="h-3.5 w-3.5 rounded border-white/20 bg-transparent accent-cyan-500"
                    />
                    隐藏内置MA线
                  </label>
                </div>

                {/* 模板管理 */}
                <TemplateManager
                  templates={templates}
                  isLoading={isLoadingTemplates}
                  onLoad={loadTemplate}
                  onDelete={deleteTemplate}
                  onSave={saveAsTemplate}
                  disabled={isBatchRunning}
                />

                {/* 参数组编辑器 */}
                <div className="mt-3">
                  <ParamGroupEditor
                    strategy={selectedStrategy}
                    paramGroups={paramGroups}
                    activeGroupId={activeGroupId}
                    onSelectGroup={setActiveGroupId}
                    onAdd={addParamGroup}
                    onRemove={removeParamGroup}
                    onDuplicate={duplicateParamGroup}
                    onUpdateParam={updateParamValue}
                    onUpdateName={updateGroupName}
                    onToggleEnabled={toggleGroupEnabled}
                    onValidationChange={setInvalidGroupIds}
                  />
                </div>
              </Card>

              {strategyError && (
                <ApiErrorAlert error={strategyError} className="mt-2 max-w-4xl" />
              )}
              {technicalError && (
                <ApiErrorAlert error={technicalError} className="mt-2 max-w-4xl" />
              )}
            </>
          )}
          </>
        ) : (
          /* AI Mode Controls */
          <div className="flex max-w-5xl flex-wrap items-center gap-2">
            <div className="relative min-w-0 flex-[1_1_220px]">
              <StockAutocomplete
                value={codeFilter}
                onChange={setCodeFilter}
                onSubmit={(code) => {
                  setCodeFilter(code);
                  handleFilter();
                }}
                placeholder="按股票代码筛选（留空为全部）"
                disabled={isRunning}
              />
            </div>
            <button
              type="button"
              onClick={handleFilter}
              disabled={isLoadingResults}
              className="btn-secondary flex items-center gap-1.5 whitespace-nowrap"
            >
              筛选
            </button>
            <div className="flex items-center gap-2 whitespace-nowrap lg:w-40 lg:justify-between">
              <span className="text-xs text-muted-text">窗口</span>
              <input
                type="number"
                min={1}
                max={120}
                value={evalDays}
                onChange={(e) => setEvalDays(e.target.value)}
                placeholder="10"
                disabled={isRunning}
                className={`${BACKTEST_COMPACT_INPUT_CLASS} w-24 text-center tabular-nums`}
              />
            </div>
            <div className="flex items-center gap-2 whitespace-nowrap">
              <span className="text-xs text-muted-text">从</span>
              <input
                type="date"
                aria-label="分析日期从"
                value={analysisDateFrom}
                onChange={(e) => setAnalysisDateFrom(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isRunning}
                className={`${BACKTEST_COMPACT_INPUT_CLASS} w-40 text-center tabular-nums`}
              />
            </div>
            <div className="flex items-center gap-2 whitespace-nowrap">
              <span className="text-xs text-muted-text">到</span>
              <input
                type="date"
                aria-label="分析日期到"
                value={analysisDateTo}
                onChange={(e) => setAnalysisDateTo(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isRunning}
                className={`${BACKTEST_COMPACT_INPUT_CLASS} w-40 text-center tabular-nums`}
              />
            </div>
            <button
              type="button"
              onClick={handleShowNextDay}
              disabled={isLoadingResults || isLoadingPerf}
              className={`backtest-force-btn ${isNextDayValidation ? 'active' : ''}`}
            >
              <span className="dot" />
              次日验证
            </button>
            <button
              type="button"
              onClick={() => setForceRerun(!forceRerun)}
              disabled={isRunning}
              className={`backtest-force-btn ${forceRerun ? 'active' : ''}`}
            >
              <span className="dot" />
              强制重跑
            </button>
            <button
              type="button"
              onClick={handleRun}
              disabled={isRunning}
              className="btn-primary flex items-center gap-1.5 whitespace-nowrap"
            >
              {isRunning ? (
                <>
                  <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  运行中...
                </>
              ) : (
                '运行回测'
              )}
            </button>
          </div>
        )}
        {runResult && (
          <div className="mt-2 max-w-4xl">
            <RunSummary data={runResult} />
          </div>
        )}
        {runError && (
          <ApiErrorAlert error={runError} className="mt-2 max-w-4xl" />
        )}
        {!isTechnicalMode && (
          <p className="mt-2 text-xs text-muted-text">
            {isNextDayValidation
              ? '次日验证模式将 AI 预测与下一交易日收盘价进行比较。'
              : '使用窗口 = 1 来对比 AI 预测与下一交易日收盘价。'}
          </p>
        )}
      </header>

      {/* Main content */}
      <main className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-3 lg:flex-row">
        {isTechnicalMode ? (
          <>
            {/* Left sidebar - Batch Overview */}
            <div className="flex max-h-[38vh] flex-col gap-3 overflow-y-auto lg:max-h-none lg:w-60 lg:flex-shrink-0">
              {selectedStrategy ? (
                <Card variant="gradient" padding="md" className="animate-fade-in">
                  <div className="mb-3">
                    <span className="label-uppercase">策略概览</span>
                  </div>
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between">
                      <span className="text-muted-text">策略</span>
                      <span className="text-secondary-text font-mono">{selectedStrategy.name}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-text">类别</span>
                      <span className="text-secondary-text font-mono">{selectedStrategy.category}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-text">参数组</span>
                      <span className="text-secondary-text font-mono">{paramGroups.filter(g => g.enabled).length} / {paramGroups.length}</span>
                    </div>
                    {batchResults && batchResults.length > 0 && (
                      <>
                        <div className="mt-2 pt-2 border-t border-white/5">
                          <span className="label-uppercase mb-1 block">回测结果</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-text">最佳参数组</span>
                          <span className="text-success font-mono">
                            {batchResults.reduce((best, r) => {
                              const bestFinal = best.equityCurve[best.equityCurve.length - 1]?.strategyValue || 0;
                              const rFinal = r.equityCurve[r.equityCurve.length - 1]?.strategyValue || 0;
                              return rFinal > bestFinal ? r : best;
                            }, batchResults[0])?.group.name}
                          </span>
                        </div>
                      </>
                    )}
                  </div>
                </Card>
              ) : (
                <EmptyState
                  title="加载中"
                  description="正在加载策略配置..."
                  className="h-full min-h-[12rem] border-dashed bg-card/45 shadow-none"
                />
              )}
            </div>

            {/* Right content - Batch Results */}
            <section className="min-h-0 flex-1 overflow-y-auto">
              {!batchResults ? (
                <EmptyState
                  title="等待运行"
                  description="选择策略、配置参数组，点击运行批量回测。"
                  className="backtest-empty-state border-dashed"
                  icon={(
                    <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                  )}
                />
              ) : (
                <div className="animate-fade-in space-y-4">
                  <div className="backtest-table-toolbar">
                    <div className="backtest-table-toolbar-meta">
                      <span className="label-uppercase">批量回测结果对比</span>
                      <span className="text-xs text-secondary-text">
                        {selectedStrategy?.name} · {batchResults.length} 组参数 · {batchResults[0]?.stockResult?.code ?? '--'}
                      </span>
                    </div>
                  </div>
                  <div className="space-y-4">
                    {batchResults.map((result) => (
                      <ParamGroupResultRow key={result.group.id} result={result} />
                    ))}
                  </div>
                </div>
              )}
            </section>
          </>
        ) : (
          <>
            {/* Left sidebar - Performance */}
            <div className="flex max-h-[38vh] flex-col gap-3 overflow-y-auto lg:max-h-none lg:w-60 lg:flex-shrink-0">
              {isLoadingPerf ? (
                <div className="flex items-center justify-center py-8">
                  <div className="backtest-spinner sm" />
                </div>
              ) : overallPerf ? (
                <PerformanceCard metrics={overallPerf} title="整体绩效" />
              ) : (
                <EmptyState
                  title="暂无指标"
                  description="运行回测以生成组合级绩效指标。"
                  className="h-full min-h-[12rem] border-dashed bg-card/45 shadow-none"
                />
              )}

              {stockPerf && (
                <PerformanceCard metrics={stockPerf} title={`${stockPerf.code || codeFilter}`} />
              )}
            </div>

            {/* Right content - Results table */}
            <section className="min-h-0 flex-1 overflow-y-auto">
          {pageError ? (
            <ApiErrorAlert error={pageError} className="mb-3" />
          ) : null}
          {isLoadingResults ? (
            <div className="flex flex-col items-center justify-center h-64">
              <div className="backtest-spinner md" />
              <p className="mt-3 text-secondary-text text-sm">加载结果中...</p>
            </div>
          ) : results.length === 0 ? (
            <EmptyState
              title="暂无结果"
              description="运行回测以评估历史分析准确度"
              className="backtest-empty-state border-dashed"
              icon={(
                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
              )}
            />
          ) : (
            <div className="animate-fade-in">
              <div className="backtest-table-toolbar">
                <div className="backtest-table-toolbar-meta">
                  <span className="label-uppercase">{isNextDayValidation ? '次日验证' : '结果集'}</span>
                  <span className="text-xs text-secondary-text">
                    {codeFilter.trim() ? `已筛选: ${codeFilter.trim()}` : '全部股票'}
                    {evalDays ? ` · ${evalDays} 天窗口` : ''}
                    {analysisDateFrom ? ` · 从 ${analysisDateFrom}` : ''}
                    {analysisDateTo ? ` · 到 ${analysisDateTo}` : ''}
                  </span>
                </div>
                <span className="backtest-table-scroll-hint">小屏幕请横向滚动</span>
              </div>
              <div className="backtest-table-wrapper">
                <table className="backtest-table min-w-[840px] w-full text-sm">
                  <thead className="backtest-table-head">
                    <tr className="text-left">
                      <th className="backtest-table-head-cell">股票</th>
                      <th className="backtest-table-head-cell">分析日期</th>
                      <th className="backtest-table-head-cell">AI 预测</th>
                      <th className="backtest-table-head-cell">
                        {showNextDayActualColumns ? '实际' : '窗口收益'}
                      </th>
                      <th className="backtest-table-head-cell">
                        {showNextDayActualColumns ? '准确度' : '方向匹配'}
                      </th>
                      <th className="backtest-table-head-cell">结果</th>
                      <th className="backtest-table-head-cell">状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.map((row) => (
                      <tr
                        key={row.analysisHistoryId}
                        className="backtest-table-row"
                      >
                        <td className="backtest-table-cell backtest-table-code">
                          <div className="flex flex-col">
                            <span>{row.code}</span>
                            <span className="text-xs text-muted-text">{row.stockName || '--'}</span>
                          </div>
                        </td>
                        <td className="backtest-table-cell text-secondary-text">{row.analysisDate || '--'}</td>
                        <td className="backtest-table-cell max-w-[220px] text-foreground">
                          {(row.trendPrediction || row.operationAdvice) ? (
                            <Tooltip
                              content={[row.trendPrediction, row.operationAdvice].filter(Boolean).join(' / ')}
                              focusable
                            >
                              <div className="flex flex-col gap-1">
                                <span className="block truncate">{row.trendPrediction || '--'}</span>
                                <span className="block truncate text-xs text-secondary-text">{row.operationAdvice || '--'}</span>
                              </div>
                            </Tooltip>
                          ) : (
                            '--'
                          )}
                        </td>
                        <td className="backtest-table-cell">
                          <div className="flex items-center gap-2">
                            {actualMovementBadge(row.actualMovement)}
                            <span className={
                              row.actualReturnPct != null
                                ? row.actualReturnPct > 0 ? 'text-success' : row.actualReturnPct < 0 ? 'text-danger' : 'text-secondary-text'
                                : 'text-muted-text'
                            }>
                              {pct(row.actualReturnPct)}
                            </span>
                          </div>
                        </td>
                        <td className="backtest-table-cell">
                          <span className="flex items-center gap-2">
                            {boolIcon(row.directionCorrect)}
                            <span className="text-muted-text">{row.directionExpected || ''}</span>
                          </span>
                        </td>
                        <td className="backtest-table-cell">{outcomeBadge(row.outcome)}</td>
                        <td className="backtest-table-cell">{statusBadge(row.evalStatus)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="mt-4">
                <Pagination
                  currentPage={currentPage}
                  totalPages={totalPages}
                  onPageChange={handlePageChange}
                />
              </div>

              <p className="text-xs text-muted-text text-center mt-2">
                共 {totalResults} 条结果 · 第 {currentPage} 页，共 {Math.max(totalPages, 1)} 页
              </p>
            </div>
          )}
        </section>
          </>
        )}
      </main>
    </div>
  );
};

export default BacktestPage;
