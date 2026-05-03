/**
 * 纯算法技术面回测类型定义
 * 与现有 AI 回测完全独立
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
