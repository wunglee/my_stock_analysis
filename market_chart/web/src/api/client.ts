import axios, { AxiosError } from 'axios';
import type { AxiosInstance } from 'axios';
import type { ApiResponse } from '../types';

const API_BASE_URL = '/api/v1';

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response) {
      return Promise.reject(
        new Error(`HTTP ${error.response.status}: ${error.response.statusText}`)
      );
    }
    return Promise.reject(error);
  }
);

// ========== 市场相关 API ==========

export interface MarketConfigItem {
  code: string;
  name: string;
  icon: string;
  timezone: string;
  currency: string;
  trading_hours: string;
  detailed_trading_hours?: {
    open: string;
    close: string;
    lunch_start?: string;
    lunch_end?: string;
    description?: string;
    timezone?: string;
  };
}

export interface ProviderConfig {
  id: string;
  name: string;
  type: string;
  available: boolean;
  status: string;
  needsConfig: boolean;
  params: Array<{
    name: string;
    label: string;
    type: string;
    placeholder: string;
    required: boolean;
  }>;
  markets: string[];
}

export interface FullMarketsConfig {
  markets: MarketConfigItem[];
  providers: ProviderConfig[];
  market_sources: Record<string, string>;
  credentials: Record<string, Record<string, unknown>>;
}

export async function fetchMarketsConfig() {
  const { data } = await apiClient.get<ApiResponse<FullMarketsConfig>>('/markets/config');
  return data;
}

export async function saveMarketsConfig(marketSources: Record<string, string>) {
  const { data } = await apiClient.put<ApiResponse<{ message: string }>>('/markets/config', {
    market_sources: marketSources,
  });
  return data;
}

export async function fetchDefaultIndices(market: string) {
  const { data } = await apiClient.get<ApiResponse<
    Record<string, Array<{ id: string; name: string; type?: string }>>
  >>(`/markets/default-indices?market=${encodeURIComponent(market)}`);
  return data;
}

// ========== 图表数据 API ==========

export interface ChartDataParams {
  symbol: string;
  period?: string;
  count?: number;
  before?: string;
  indicators?: string;
}

export async function fetchChartData(params: ChartDataParams) {
  const searchParams = new URLSearchParams();
  searchParams.set('symbol', params.symbol);
  if (params.period) searchParams.set('period', params.period);
  if (params.count) searchParams.set('count', String(params.count));
  if (params.before) searchParams.set('before', params.before);
  if (params.indicators) searchParams.set('indicators', params.indicators);

  const { data } = await apiClient.get<ApiResponse<import('../types').ChartDataResponse>>(
    `/chart/data?${searchParams.toString()}`
  );
  return data;
}

// ========== 分时数据 API ==========

export interface IntradayParams {
  symbol: string;
  tick_range?: string;
}

export async function fetchIntradayData(params: IntradayParams) {
  const searchParams = new URLSearchParams();
  searchParams.set('symbol', params.symbol);
  if (params.tick_range) searchParams.set('tick_range', params.tick_range);

  const { data } = await apiClient.get<ApiResponse<import('../types').IntradayResponse>>(
    `/intraday/data?${searchParams.toString()}`
  );
  return data;
}

// ========== 实时数据 API ==========

export async function fetchKlineRealtime(symbol: string, period?: string) {
  const searchParams = new URLSearchParams();
  searchParams.set('symbol', symbol);
  if (period) searchParams.set('period', period);

  const { data } = await apiClient.get<ApiResponse<import('../types').KlineDataPoint[]>>(
    `/data/kline/realtime?${searchParams.toString()}`
  );
  return data;
}

// ========== 数据源管理 API ==========

export async function fetchProviders() {
  const { data } = await apiClient.get<ApiResponse<import('../types').Provider[]>>('/providers');
  return data;
}

export async function testProviderConnection(providerId: string, credentials: Record<string, string>) {
  const { data } = await apiClient.post<ApiResponse<{ message: string }>>(
    `/providers/${providerId}/test`,
    {
      credentials,
      proxy: {
        http: 'http://127.0.0.1:8002',
        https: 'http://127.0.0.1:8002',
        socks5: 'socks5://127.0.0.1:1081',
      },
    }
  );
  return data;
}

export async function createProvider(providerData: Omit<import('../types').Provider, 'id'>) {
  const { data } = await apiClient.post<ApiResponse<import('../types').Provider>>(
    '/providers',
    providerData
  );
  return data;
}

export async function updateProvider(id: string, providerData: Partial<import('../types').Provider>) {
  const { data } = await apiClient.put<ApiResponse<import('../types').Provider>>(
    `/providers/${id}`,
    providerData
  );
  return data;
}

export async function deleteProvider(id: string) {
  const { data } = await apiClient.delete<ApiResponse<void>>(`/providers/${id}`);
  return data;
}

// ========== 凭证管理 API ==========

export async function fetchCredentials() {
  const { data } = await apiClient.get<ApiResponse<import('../types').Credential[]>>('/credentials');
  return data;
}

export async function createCredential(credentialData: Omit<import('../types').Credential, 'id'>) {
  const { data } = await apiClient.post<ApiResponse<import('../types').Credential>>(
    '/credentials',
    credentialData
  );
  return data;
}

export async function deleteCredential(id: string) {
  const { data } = await apiClient.delete<ApiResponse<void>>(`/credentials/${id}`);
  return data;
}

export default apiClient;
