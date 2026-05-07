import type React from 'react';
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Check, Minus, X } from 'lucide-react';
import { StockAutocomplete } from '../components/StockAutocomplete';
import { backtestApi } from '../api/backtest';
import type { ParsedApiError } from '../api/error';
import { getParsedApiError } from '../api/error';
import { ApiErrorAlert, Card, Badge, EmptyState, Pagination, StatusDot, Tooltip } from '../components/common';
import type {
  BacktestResultItem,
  BacktestRunResponse,
  PerformanceMetrics,
} from '../types/backtest';
import type { TechnicalBacktestResult, TechnicalBacktestStockResult } from '../types/technicalBacktest';

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

// ============ Technical Result Detail ============

const TechnicalResultDetail: React.FC<{ result: TechnicalBacktestStockResult }> = ({ result }) => {
  const klineContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // 确保 kline_chart.js 已加载
    if (typeof window.KlineChart === 'undefined') {
      console.warn('KlineChart not loaded yet');
      return;
    }
    // 回测场景禁用实时K线更新，避免请求不存在的端点
    window.KlineChart.setRealtimeUpdateEnabled(false);
    // 设置当前股票
    window.KlineChart.setCurrent(
      { id: result.code, name: result.stockName },
      'CN',
      false,
    );
  }, [result.code, result.stockName]);

  const actionBadge = (action: string) => {
    switch (action) {
      case 'buy': return <Badge variant="success">买入</Badge>;
      case 'sell': return <Badge variant="danger">卖出</Badge>;
      case 'hold': return <Badge variant="warning">持有</Badge>;
      default: return <Badge variant="default">观望</Badge>;
    }
  };

  return (
    <div className="animate-fade-in space-y-4 px-4 pb-4">
      {/* K-Line Chart */}
      <div>
        <h4 className="text-xs font-medium text-muted-text mb-2 uppercase">K线信号叠加</h4>
        <div className="rounded-lg border border-white/5 bg-card/20 overflow-hidden">
          <div ref={klineContainerRef} id="klineContainer" style={{ minHeight: 720 }} />
        </div>
      </div>

      {/* Rules */}
      <div>
        <h4 className="text-xs font-medium text-muted-text mb-2 uppercase">发现规律</h4>
        <div className="space-y-1.5">
          {result.rules.map((rule, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg bg-white/[0.03] px-3 py-2">
              <div className="flex items-center gap-2 min-w-0">
                <Badge variant={rule.winRate >= 0.6 ? 'success' : rule.winRate >= 0.5 ? 'warning' : 'default'}>
                  {rule.name}
                </Badge>
                <span className="text-xs text-secondary-text truncate">{rule.condition}</span>
              </div>
              <div className="flex items-center gap-3 text-xs flex-shrink-0">
                <span className="text-muted-text">样本 {rule.sampleCount}</span>
                <span className={rule.winRate >= 0.6 ? 'text-success' : 'text-secondary-text'}>
                  胜率 {(rule.winRate * 100).toFixed(0)}%
                </span>
                <span className="text-muted-text">置信 {(rule.confidence * 100).toFixed(0)}%</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Signals */}
      <div>
        <h4 className="text-xs font-medium text-muted-text mb-2 uppercase">交易信号</h4>
        <div className="backtest-table-wrapper">
          <table className="backtest-table min-w-[600px] w-full text-xs">
            <thead className="backtest-table-head">
              <tr>
                <th className="backtest-table-head-cell">日期</th>
                <th className="backtest-table-head-cell">操作</th>
                <th className="backtest-table-head-cell">入场价</th>
                <th className="backtest-table-head-cell">止损</th>
                <th className="backtest-table-head-cell">止盈</th>
                <th className="backtest-table-head-cell">理由</th>
                <th className="backtest-table-head-cell">置信</th>
              </tr>
            </thead>
            <tbody>
              {result.signals.map((sig, i) => (
                <tr key={i} className="backtest-table-row">
                  <td className="backtest-table-cell">{sig.date}</td>
                  <td className="backtest-table-cell">{actionBadge(sig.action)}</td>
                  <td className="backtest-table-cell">{sig.entryPrice ?? '--'}</td>
                  <td className="backtest-table-cell">{sig.stopLoss ?? '--'}</td>
                  <td className="backtest-table-cell">{sig.takeProfit ?? '--'}</td>
                  <td className="backtest-table-cell">
                    <span className="text-xs text-secondary-text">{sig.reasons.join(', ')}</span>
                  </td>
                  <td className="backtest-table-cell">
                    <span className={sig.confidence >= 0.7 ? 'text-success' : 'text-warning'}>
                      {(sig.confidence * 100).toFixed(0)}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Evaluations */}
      <div>
        <h4 className="text-xs font-medium text-muted-text mb-2 uppercase">回测验证</h4>
        <div className="backtest-table-wrapper">
          <table className="backtest-table min-w-[600px] w-full text-xs">
            <thead className="backtest-table-head">
              <tr>
                <th className="backtest-table-head-cell">信号日</th>
                <th className="backtest-table-head-cell">操作</th>
                <th className="backtest-table-head-cell">结果</th>
                <th className="backtest-table-head-cell">收益</th>
                <th className="backtest-table-head-cell">方向</th>
                <th className="backtest-table-head-cell">止损</th>
                <th className="backtest-table-head-cell">止盈</th>
              </tr>
            </thead>
            <tbody>
              {result.evaluations.map((ev, i) => (
                <tr key={i} className="backtest-table-row">
                  <td className="backtest-table-cell">{ev.signalDate}</td>
                  <td className="backtest-table-cell">{ev.action}</td>
                  <td className="backtest-table-cell">{outcomeBadge(ev.outcome)}</td>
                  <td className={`backtest-table-cell ${ev.stockReturnPct > 0 ? 'text-success' : ev.stockReturnPct < 0 ? 'text-danger' : ''}`}>
                    {ev.stockReturnPct > 0 ? '+' : ''}{ev.stockReturnPct.toFixed(1)}%
                  </td>
                  <td className="backtest-table-cell">{boolIcon(ev.directionCorrect)}</td>
                  <td className="backtest-table-cell">{boolIcon(ev.hitStopLoss)}</td>
                  <td className="backtest-table-cell">{boolIcon(ev.hitTakeProfit)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

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

  // Input state
  const [codeFilter, setCodeFilter] = useState('');
  const [analysisDateFrom, setAnalysisDateFrom] = useState('');
  const [analysisDateTo, setAnalysisDateTo] = useState('');
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
  const [isTechnicalRunning, setIsTechnicalRunning] = useState(false);
  const [technicalError, setTechnicalError] = useState<ParsedApiError | null>(null);
  const [technicalResult, setTechnicalResult] = useState<TechnicalBacktestResult | null>(null);
  const [expandedStockCode, setExpandedStockCode] = useState<string | null>(null);
  const [technicalCodes, setTechnicalCodes] = useState('');
  const [technicalStartDate, setTechnicalStartDate] = useState('');
  const [technicalEndDate, setTechnicalEndDate] = useState('');
  const [technicalEvalDays, setTechnicalEvalDays] = useState('10');

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
      console.error('Failed to fetch backtest results:', err);
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
      console.error('Failed to fetch performance:', err);
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
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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

  // Run technical backtest (real API)
  const handleRunTechnical = async () => {
    const codes = technicalCodes
      .split(/[,，\s]+/)
      .map((c) => c.trim())
      .filter(Boolean);
    if (codes.length === 0) return;
    if (!technicalStartDate || !technicalEndDate) return;

    setIsTechnicalRunning(true);
    setTechnicalResult(null);
    setTechnicalError(null);
    setExpandedStockCode(null);
    try {
      const result = await backtestApi.runTechnical({
        codes,
        startDate: technicalStartDate,
        endDate: technicalEndDate,
        evalWindowDays: parseInt(technicalEvalDays, 10) || 10,
      });
      setTechnicalResult(result);
    } catch (err) {
      setTechnicalError(getParsedApiError(err));
    } finally {
      setIsTechnicalRunning(false);
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
            onClick={() => setIsTechnicalMode(false)}
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
            onClick={() => setIsTechnicalMode(true)}
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
          {/* Technical Mode Controls */}
          <div className="flex max-w-5xl flex-wrap items-center gap-2">
            <div className="relative min-w-0 flex-[1_1_220px]">
              <StockAutocomplete
                value={technicalCodes}
                onChange={setTechnicalCodes}
                searchQuery={technicalSearchQuery}
                onSubmit={(code, _name, source) => {
                  if (source === 'autocomplete') {
                    const tokens = technicalCodes
                      .split(/[,，\s]+/)
                      .map((c) => c.trim())
                      .filter(Boolean);
                    // 去掉最后一个 token（用户正在搜索的部分输入），替换为选中代码
                    const existing = tokens.slice(0, -1);
                    if (!existing.includes(code)) {
                      setTechnicalCodes(
                        existing.length > 0 ? `${existing.join(', ')}, ${code}` : code,
                      );
                    } else {
                      setTechnicalCodes(existing.join(', '));
                    }
                  }
                }}
                placeholder="输入股票代码，逗号分隔（如：600519,000858）"
                disabled={isTechnicalRunning}
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
              onClick={handleRunTechnical}
              disabled={isTechnicalRunning}
              className="btn-primary flex items-center gap-1.5 whitespace-nowrap"
            >
              {isTechnicalRunning ? (
                <>
                  <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  分析中...
                </>
              ) : (
                '运行纯技术回测'
              )}
            </button>
          </div>
          {technicalError && (
            <ApiErrorAlert error={technicalError} className="mt-2 max-w-4xl" />
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
            {/* Left sidebar - Technical Summary */}
            <div className="flex max-h-[38vh] flex-col gap-3 overflow-y-auto lg:max-h-none lg:w-60 lg:flex-shrink-0">
              {technicalResult ? (
                <Card variant="gradient" padding="md" className="animate-fade-in">
                  <div className="mb-3">
                    <span className="label-uppercase">纯技术回测概览</span>
                  </div>
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between">
                      <span className="text-muted-text">股票数</span>
                      <span className="text-secondary-text font-mono">{technicalResult.meta.codes.length}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-text">日期范围</span>
                      <span className="text-secondary-text font-mono">{technicalResult.meta.dateRange[0]} ~ {technicalResult.meta.dateRange[1]}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-text">评估窗口</span>
                      <span className="text-secondary-text font-mono">{technicalResult.meta.evalWindowDays} 天</span>
                    </div>
                  </div>
                  {technicalResult.crossStock && technicalResult.crossStock.correlations.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-white/5">
                      <span className="label-uppercase mb-2 block">跨股票相关性</span>
                      {technicalResult.crossStock.correlations.map((corr, i) => (
                        <div key={i} className="flex justify-between text-xs">
                          <span className="text-muted-text">{corr.codeA} ↔ {corr.codeB}</span>
                          <span className={`font-mono ${corr.priceCorrelation >= 0.6 ? 'text-success' : 'text-secondary-text'}`}>
                            {corr.priceCorrelation.toFixed(2)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </Card>
              ) : (
                <EmptyState
                  title="暂无数据"
                  description="运行纯技术回测以查看结果。"
                  className="h-full min-h-[12rem] border-dashed bg-card/45 shadow-none"
                />
              )}
            </div>

            {/* Right content - Technical Results */}
            <section className="min-h-0 flex-1 overflow-y-auto">
              {!technicalResult ? (
                <EmptyState
                  title="等待运行"
                  description="输入股票代码和日期范围，点击运行纯技术回测。"
                  className="backtest-empty-state border-dashed"
                  icon={(
                    <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                  )}
                />
              ) : (
                <div className="animate-fade-in space-y-3">
                  <div className="backtest-table-toolbar">
                    <div className="backtest-table-toolbar-meta">
                      <span className="label-uppercase">纯技术回测结果</span>
                      <span className="text-xs text-secondary-text">
                        {technicalResult.meta.codes.join(', ')} · {technicalResult.meta.dateRange[0]} ~ {technicalResult.meta.dateRange[1]}
                      </span>
                    </div>
                  </div>
                  <div className="space-y-2">
                    {Object.values(technicalResult.perStock).map((stock) => (
                      <div key={stock.code} className="rounded-xl border border-white/5 bg-card/30 overflow-hidden">
                        {/* Summary row - clickable */}
                        <div
                          className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-white/[0.03] transition-colors"
                          onClick={() => setExpandedStockCode(expandedStockCode === stock.code ? null : stock.code)}
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <span className="text-sm font-medium text-foreground">{stock.code}</span>
                            <span className="text-xs text-muted-text truncate">{stock.stockName}</span>
                            <span className="text-xs text-muted-text">{stock.dateRange}</span>
                          </div>
                          <div className="flex items-center gap-4 text-xs flex-shrink-0">
                            <span className="text-muted-text">信号 <span className="text-secondary-text font-mono">{stock.totalSignals}</span></span>
                            <span className={stock.winRate >= 0.6 ? 'text-success' : 'text-warning'}>
                              胜率 <span className="font-mono">{(stock.winRate * 100).toFixed(0)}%</span>
                            </span>
                            <span className={stock.avgReturn >= 0 ? 'text-success' : 'text-danger'}>
                              均收 <span className="font-mono">{stock.avgReturn > 0 ? '+' : ''}{stock.avgReturn.toFixed(1)}%</span>
                            </span>
                            <span className="text-danger">
                              回撤 <span className="font-mono">{stock.maxDrawdown.toFixed(1)}%</span>
                            </span>
                            <svg
                              className={`h-4 w-4 text-muted-text transition-transform ${expandedStockCode === stock.code ? 'rotate-180' : ''}`}
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                            >
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                            </svg>
                          </div>
                        </div>

                        {/* Expanded detail */}
                        {expandedStockCode === stock.code && (
                          <TechnicalResultDetail result={stock} />
                        )}
                      </div>
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
