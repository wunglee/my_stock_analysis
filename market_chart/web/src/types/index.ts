// API Response wrapper
export interface ApiResponse<T> {
  status: 'success' | 'error';
  data?: T;
  message?: string;
  error_code?: string;
  timestamp?: string;
}

// Market configuration
export interface MarketConfig {
  code: string;
  name: string;
  icon: string;
  timezone: string;
  currency: string;
  trading_hours: string;
  detailed_trading_hours?: {
    pre_market?: string;
    morning?: string;
    lunch_start?: string;
    lunch_end?: string;
    afternoon?: string;
    after_hours?: string;
  };
}

export interface MarketsConfigResponse {
  markets: MarketConfig[];
  market_sources: Record<string, string>;
}

// Stock / Index item
export interface StockItem {
  id: string;
  name: string;
  type?: 'index' | 'stock' | 'custom';
}

// K-line data point
export interface KlineDataPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// Technical indicator data
export interface IndicatorData {
  vol?: number[];
  macd?: { dif: number[]; dea: number[]; hist: number[] };
  rsi?: number[];
  kdj?: { k: number[]; d: number[]; j: number[] };
  obv?: number[];
}

// Chart data response
export interface ChartDataResponse {
  kline: KlineDataPoint[];
  indicators: IndicatorData;
  events?: Array<{
    date: string;
    type: string;
    description: string;
  }>;
  ma5?: number[];
  ma10?: number[];
  ma20?: number[];
}

// Intraday data point
export interface IntradayDataPoint {
  time: string;
  price: number;
  volume: number;
  avg_price?: number;
}

export interface IntradayResponse {
  prices: number[];
  volumes: number[];
  avg_prices: number[];
  times: string[];
  pre_close: number;
  order_book?: OrderBook;
  tickers?: TickerData;
}

// Order book
export interface OrderBook {
  bids: Array<{ price: number; volume: number }>;
  asks: Array<{ price: number; volume: number }>;
  message?: string;
}

// Trade ticker
export interface TickerItem {
  time: string;
  price: number;
  volume: number;
  type: 'buy' | 'sell';
}

export interface TickerData {
  items: TickerItem[];
  message?: string;
}

// Provider
export interface Provider {
  id: string;
  name: string;
  type: string;
  status: string;
  available: boolean;
  adapter_module?: string;
  adapter_class?: string;
}

// Credential
export interface Credential {
  id: string;
  provider_id: string;
  name: string;
  key: string;
  created_at?: string;
  updated_at?: string;
}

// Data mode
export type DataMode = 'real' | 'mock';
export type TradingPhase = 'before_open' | 'trading' | 'after_close';
export type ChartType = 'intraday' | 'kline';
export type KlinePeriod = 'daily' | 'weekly' | 'monthly';
export type IndicatorType = 'VOL' | 'MACD' | 'RSI' | 'KDJ' | 'OBV';
