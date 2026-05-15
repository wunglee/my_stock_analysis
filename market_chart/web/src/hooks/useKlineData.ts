import { useEffect, useState, useCallback, useRef } from 'react'
import type { KlineDataPoint, IndicatorData, KlinePeriod, IndicatorType } from '../types'
import { fetchChartData, fetchKlineRealtime } from '../api/client.ts'

export function useKlineData(symbol: string, period: KlinePeriod = 'daily') {
  const [kline, setKline] = useState<KlineDataPoint[]>([])
  const [indicators, setIndicators] = useState<IndicatorData>({})
  const [ma5, setMa5] = useState<number[]>([])
  const [ma10, setMa10] = useState<number[]>([])
  const [ma20, setMa20] = useState<number[]>([])
  const [loading, setLoading] = useState(false)
  const [hasMore, setHasMore] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [activeIndicators, setActiveIndicators] = useState<IndicatorType[]>(['VOL'])
  const oldestDateRef = useRef<string | null>(null)

  // 加载K线数据
  const loadData = useCallback(
    async (before?: string) => {
      if (!symbol) return
      setLoading(true)
      setError(null)
      try {
        const res = await fetchChartData({
          symbol,
          period,
          count: 100,
          before,
          indicators: activeIndicators.join(','),
        })
        if (res.status === 'success' && res.data) {
          const newKline = res.data.kline
          if (before) {
            setKline((prev) => [...newKline, ...prev])
          } else {
            setKline(newKline)
          }
          setIndicators(res.data.indicators)
          setMa5(res.data.ma5 || [])
          setMa10(res.data.ma10 || [])
          setMa20(res.data.ma20 || [])

          if (newKline.length > 0) {
            oldestDateRef.current = newKline[0].date
          }
          setHasMore(newKline.length === 100)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : '加载K线数据失败')
      } finally {
        setLoading(false)
      }
    },
    [symbol, period]
  )

  // 初始加载
  useEffect(() => {
    setKline([])
    oldestDateRef.current = null
    loadData()
  }, [loadData])

  // 加载更多（无限滚动）
  const loadMore = useCallback(() => {
    if (loading || !hasMore || !oldestDateRef.current) return
    loadData(oldestDateRef.current)
  }, [loadData, loading, hasMore])

  // 实时更新
  useEffect(() => {
    if (!symbol) return
    const interval = setInterval(async () => {
      try {
        const res = await fetchKlineRealtime(symbol, period)
        if (res.status === 'success' && res.data && res.data.length > 0) {
          setKline((prev) => {
            const last = prev[prev.length - 1]
            const update = res.data!
            const newPoint = update[update.length - 1]
            if (last && last.date === newPoint.date) {
              return [...prev.slice(0, -1), newPoint]
            }
            return [...prev, newPoint]
          })
        }
      } catch {
        // 静默处理实时更新失败
      }
    }, 5000)

    return () => clearInterval(interval)
  }, [symbol, period])

  // 当指标类型变化时，重新加载数据
  useEffect(() => {
    if (!symbol) return
    setKline([])
    oldestDateRef.current = null
    loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIndicators])

  return {
    kline,
    indicators,
    ma5,
    ma10,
    ma20,
    loading,
    hasMore,
    error,
    loadMore,
    setActiveIndicators,
  }
}
