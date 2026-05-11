/**
 * 纯算法技术面回测类型定义
 * 与现有 AI 回测完全独立
 *
 * 本文件按迭代阶段渐进扩展：
 * - 已有类型（klineData/rules/signals/evaluations）对应现有后端 API 返回
 * - 新增类型（equityCurve/benchmarkCurve/strategyConfig/paramGroup）为 v2.0 演进所需
 *   后端未实现阶段由前端 mock 填充
 */

export interface TechnicalRule {
  name: string;
  condition: string;
  sampleCount: number;
  winRate: number;
  avgReturn5d: number;
  confidence: number;
}

export interface TechnicalSignal {
  date: string;
  action: 'buy' | 'sell' | 'hold' | 'wait';
  entryPrice: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
  reasons: string[];
  confidence: number;
}

export interface TechnicalEvaluation {
  signalDate: string;
  action: string;
  outcome: 'win' | 'loss' | 'neutral';
  stockReturnPct: number;
  hitTakeProfit: boolean;
  hitStopLoss: boolean;
  directionCorrect: boolean;
}

// ============ v2.0 新增：收益率曲线（后端未实现，前端 mock）============

export interface EquityCurvePoint {
  date: string;
  strategyValue: number;   // 策略当日权益（含交易费用）
  benchmarkValue: number;  // 基准当日权益（买入并持有）
}

export interface TradeRecord {
  id: number;
  entryDate: string;
  entryPrice: number;
  exitDate: string;
  exitPrice: number;
  returnPct: number;
  pnlAmount: number;       // 盈亏金额（已扣费用）
  holdDays: number;
  reason: string;          // 触发理由
}

// ============ v2.0 新增：策略配置（后端配置文件格式，前端 mock）============

export type ParameterType = 'number' | 'boolean';

export type ValidationRuleType = 'lessThan' | 'greaterThan';

export interface ValidationRule {
  type: ValidationRuleType;
  paramA: string;
  paramB: string;
  message: string;
}

export interface StrategyParameter {
  key: string;
  name: string;
  type: ParameterType;
  defaultValue: number | boolean;
  min?: number;
  max?: number;
  step?: number;
}

export type StrategyCategory = 'trend' | 'oscillator' | 'volatility' | 'volume';

export interface StrategyConfig {
  id: string;
  name: string;
  description: string;
  category: StrategyCategory;
  parameters: StrategyParameter[];
  validationRules: ValidationRule[];
}

// ============ v2.0 新增：参数组 ============

export interface ParamGroup {
  id: string;              // 唯一标识（如 group-1, group-2）
  name: string;            // 显示名称（如"参数组 1"）
  enabled: boolean;
  params: Record<string, number | boolean>;  // 参数 key -> 值
}

export interface ParamGroupResult {
  group: ParamGroup;
  status: 'success' | 'insufficient_data' | 'error';
  errorMessage?: string;
  stockResult: TechnicalBacktestStockResult | null;
  equityCurve: EquityCurvePoint[];
  trades: TradeRecord[];
}

// ============ P3: 参数组模板 ============

export interface BacktestTemplateItem {
  id: number;
  strategyId: string;
  name: string;
  params: ParamGroup[];
  createdAt: string;
  updatedAt: string;
}

// ============ 现有类型扩展 ============

export interface TechnicalBacktestStockResult {
  code: string;
  stockName: string;
  dateRange: string;
  totalSignals: number;
  winRate: number;
  avgReturn: number;
  maxDrawdown: number;
  klineData?: KlineData[];
  rules: TechnicalRule[];
  signals: TechnicalSignal[];
  evaluations: TechnicalEvaluation[];
  // v2.0 新增（后端未实现时由前端 mock 生成）
  equityCurve?: EquityCurvePoint[];  // 策略 vs 基准权益曲线
  trades?: TradeRecord[];            // 配对交易明细
}

export interface KlineData {
  date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  volume: number;
}

export interface TechnicalBacktestResult {
  meta: {
    mode: 'technical';
    codes: string[];
    dateRange: [string, string];
    evalWindowDays: number;
    generatedAt: string;
    // v2.0 新增（后端未实现时由前端 mock 填充）
    strategyId?: string;      // 回测使用的策略 ID
    paramGroupId?: string;    // 参数组 ID
    initialCapital?: number;  // 初始资金（默认 100000）
  };
  perStock: Record<string, TechnicalBacktestStockResult>;
  crossStock?: {
    correlations: Array<{
      codeA: string;
      codeB: string;
      priceCorrelation: number;
    }>;
  };
}
