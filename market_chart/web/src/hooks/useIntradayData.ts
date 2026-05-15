import { useEffect, useState, useCallback } from 'react'
import type { IntradayResponse } from '../types'
import { fetchIntradayData } from '../api/client.ts'

export function useIntradayData(symbol: string) {
  const [data, setData] = useState<IntradayResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!symbol) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetchIntradayData({ symbol })
      if (res.status === 'success' && res.data) {
        setData(res.data)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载分时数据失败')
    } finally {
      setLoading(false)
    }
  }, [symbol])

  useEffect(() => {
    setData(null)
    load()
  }, [load])

  // 轮询更新
  useEffect(() => {
    if (!symbol) return
    const interval = setInterval(() => {
      load()
    }, 5000)
    return () => clearInterval(interval)
  }, [load, symbol])

  return { data, loading, error, reload: load }
}
