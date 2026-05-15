import { useState, useCallback, useMemo, useEffect } from 'react'
import type { StockItem } from '../types'
import { useMarkets } from './useMarkets.ts'

export function useExplorer() {
  const { markets, selectedMarket, currentMarket, indices, stocks, loading: marketsLoading, error: marketsError, selectMarket } = useMarkets()

  const [selectedStock, setSelectedStock] = useState<string | null>(null)
  const [customStocks, setCustomStocks] = useState<StockItem[]>([])

  const allStocks = useMemo<StockItem[]>(() => {
    const defaults: StockItem[] = [
      ...indices.map((i) => ({ id: i.id, name: i.name, type: 'index' as const })),
      ...stocks.map((s) => ({ id: s.id, name: s.name, type: 'stock' as const })),
    ]
    return [...defaults, ...customStocks]
  }, [indices, stocks, customStocks])

  // 股票列表变化时，若当前选中项不在列表中，自动选中第一个
  useEffect(() => {
    if (allStocks.length > 0) {
      const hasSelected = allStocks.some((s) => s.id === selectedStock)
      if (!hasSelected) {
        setSelectedStock(allStocks[0].id)
      }
    } else {
      setSelectedStock(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allStocks])

  // 当前选中的股票对象（兼容原始JS组件的接口：{id, name, type}）
  const currentSymbolObj = useMemo(() => {
    if (selectedStock) {
      return allStocks.find((s) => s.id === selectedStock) || null
    }
    return allStocks[0] || null
  }, [selectedStock, allStocks])

  const handleSelectStock = useCallback((id: string) => {
    setSelectedStock(id)
  }, [])

  const handleRemoveStock = useCallback((id: string) => {
    setCustomStocks((prev) => prev.filter((s) => s.id !== id))
    if (selectedStock === id) {
      setSelectedStock(null)
    }
  }, [selectedStock])

  const handleAddStock = useCallback((id: string, name: string) => {
    setCustomStocks((prev) => {
      if (prev.some((s) => s.id === id)) return prev
      return [...prev, { id, name, type: 'custom' as const }]
    })
  }, [])

  return {
    markets,
    selectedMarket,
    currentMarket,
    marketsLoading,
    marketsError,
    selectMarket,
    allStocks,
    selectedStock,
    currentSymbolObj,
    handleSelectStock,
    handleRemoveStock,
    handleAddStock,
  }
}
