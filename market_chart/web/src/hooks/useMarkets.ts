import { useEffect, useState, useCallback } from 'react'
import type { MarketConfig } from '../types'
import { fetchMarketsConfig, fetchDefaultIndices } from '../api/client.ts'

declare global {
  interface Window {
    marketsConfig?: MarketConfig[]
    marketConfig?: Record<string, unknown>
  }
}

export function useMarkets() {
  const [markets, setMarkets] = useState<MarketConfig[]>([])
  const [selectedMarket, setSelectedMarket] = useState<string>('')
  const [indices, setIndices] = useState<Array<{ id: string; name: string }>>([])
  const [stocks, setStocks] = useState<Array<{ id: string; name: string }>>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 加载市场配置（只执行一次）
  useEffect(() => {
    async function load() {
      try {
        const res = await fetchMarketsConfig()
        if (res.status === 'success' && res.data) {
          const loadedMarkets = res.data.markets || []
          setMarkets(loadedMarkets)

          // 设置全局变量以兼容原始 JS 图表组件
          window.marketsConfig = loadedMarkets
          window.marketConfig = {}
          loadedMarkets.forEach((market: MarketConfig) => {
            const detailedHours = market.detailed_trading_hours || {
              open: market.trading_hours?.split('-')[0]?.trim(),
              close: market.trading_hours?.split('-')[1]?.trim(),
              lunch_start: null,
              lunch_end: null,
            }
            window.marketConfig![market.code.toUpperCase()] = {
              detailed_trading_hours: detailedHours,
              trading_hours: market.trading_hours,
              timezone: market.timezone,
              currency: market.currency,
            }
          })

          if (loadedMarkets.length > 0) {
            setSelectedMarket(loadedMarkets[0].code)
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : '加载市场配置失败')
      } finally {
        setLoading(false)
      }
    }
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 加载默认指数和股票
  useEffect(() => {
    if (!selectedMarket) return
    async function load() {
      try {
        const res = await fetchDefaultIndices(selectedMarket)
        if (res.status === 'success' && res.data) {
          const marketData = res.data[selectedMarket] || []
          const idxs = marketData
            .filter((item) => (item.type || '').toLowerCase() === 'index')
            .map((item) => ({ id: item.id, name: item.name }))
          const stks = marketData
            .filter((item) => (item.type || '').toLowerCase() === 'stock')
            .map((item) => ({ id: item.id, name: item.name }))
          setIndices(idxs)
          setStocks(stks)
        }
      } catch (err) {
        console.error('加载默认指数失败:', err)
      }
    }
    load()
  }, [selectedMarket])

  const currentMarket = markets.find((m) => m.code === selectedMarket)

  const selectMarket = useCallback((code: string) => {
    setSelectedMarket(code)
    setIndices([])
    setStocks([])
  }, [])

  return {
    markets,
    selectedMarket,
    currentMarket,
    indices,
    stocks,
    loading,
    error,
    selectMarket,
  }
}
