import { useEffect, useRef, useMemo } from 'react'
import * as echarts from 'echarts'
import type { IntradayResponse } from '../types'
import OrderBook from './OrderBook.tsx'
import TradeTicker from './TradeTicker.tsx'

interface IntradayChartProps {
  data: IntradayResponse | null
}

function generateTradingTimes(startH: number, startM: number, endH: number, endM: number, stepSec = 5): string[] {
  const times: string[] = []
  const startSec = startH * 3600 + startM * 60
  const endSec = endH * 3600 + endM * 60
  for (let s = startSec; s <= endSec; s += stepSec) {
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    const sec = s % 60
    if (h > endH || (h === endH && m > endM)) continue
    const ts = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
    if (!times.includes(ts)) times.push(ts)
  }
  return times
}

function getTradingTimesForMarket(marketCode?: string): { times: string[]; hasLunch: boolean } {
  if (!marketCode || marketCode === 'CN') {
    const morning = generateTradingTimes(9, 30, 11, 30)
    const afternoon = generateTradingTimes(13, 0, 15, 0)
    return { times: [...morning, ...afternoon], hasLunch: true }
  }
  if (marketCode === 'HK') {
    const morning = generateTradingTimes(9, 30, 12, 0)
    const afternoon = generateTradingTimes(13, 0, 16, 0)
    return { times: [...morning, ...afternoon], hasLunch: true }
  }
  const us = generateTradingTimes(9, 30, 16, 0)
  return { times: us, hasLunch: false }
}

export default function IntradayChart({ data }: IntradayChartProps) {
  const priceContainerRef = useRef<HTMLDivElement>(null)
  const volumeContainerRef = useRef<HTMLDivElement>(null)
  const priceChartRef = useRef<echarts.ECharts | null>(null)
  const volumeChartRef = useRef<echarts.ECharts | null>(null)

  const { times: fullTimes, hasLunch } = useMemo(() => getTradingTimesForMarket('CN'), [])

  const chartData = useMemo(() => {
    if (!data) return null
    const prices = data.prices || []
    const volumes = data.volumes || []
    const avgPrices = data.avg_prices || []
    const chartTimes = data.times?.length ? data.times : fullTimes.slice(0, prices.length)
    return { prices, volumes, avgPrices, times: chartTimes }
  }, [data, fullTimes])

  const markLineData = useMemo(() => {
    const lines: Array<{ xAxis: string; label: { formatter: string }; lineStyle: { type: string; color: string } }> = []
    if (hasLunch && fullTimes.length > 0) {
      const amEnd = fullTimes.find((t) => t.startsWith('11:30'))
      const pmStart = fullTimes.find((t) => t.startsWith('13:00'))
      if (amEnd) {
        lines.push({
          xAxis: amEnd,
          label: { formatter: '午休' },
          lineStyle: { type: 'dashed', color: '#9ca3af' },
        })
      }
      if (pmStart) {
        lines.push({
          xAxis: pmStart,
          label: { formatter: '' },
          lineStyle: { type: 'dashed', color: '#9ca3af' },
        })
      }
    }
    return lines
  }, [hasLunch, fullTimes])

  const priceOption = useMemo<echarts.EChartsCoreOption>(() => {
    if (!chartData) return {}
    const { prices, avgPrices, times } = chartData

    return {
      title: { text: '分时价格', left: 'center', textStyle: { fontSize: 12 } },
      tooltip: {
        trigger: 'axis',
        formatter: (params: unknown) => {
          const arr = params as Array<{ axisValue: string; seriesName: string; value: number; marker: string }>
          if (!arr?.length) return ''
          let result = `<div style="font-weight:600;margin-bottom:4px;">${arr[0].axisValue}</div>`
          arr.forEach((p) => {
            result += `<div>${p.marker} ${p.seriesName}: ${p.value?.toFixed(2) ?? '-'}</div>`
          })
          return result
        },
      },
      grid: { left: '50px', right: '50px', top: '40px', bottom: '30px' },
      xAxis: {
        type: 'category',
        data: times,
        axisLabel: {
          color: '#6b7280',
          formatter: (value: string) => (value.endsWith(':00') ? value.slice(0, 5) : ''),
        },
        axisLine: { lineStyle: { color: '#e5e7eb' } },
      },
      yAxis: {
        type: 'value',
        scale: true,
        splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } },
        axisLabel: { color: '#6b7280' },
      },
      series: [
        {
          name: '价格',
          type: 'line',
          data: prices,
          smooth: false,
          showSymbol: false,
          lineStyle: { color: '#2563eb', width: 1.5 },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(37, 99, 235, 0.15)' },
                { offset: 1, color: 'rgba(37, 99, 235, 0)' },
              ],
            },
          },
          markLine: {
            symbol: 'none',
            silent: true,
            animation: false,
            data: [
              ...markLineData,
              {
                yAxis: data?.pre_close ?? 0,
                label: { formatter: '昨收' },
                lineStyle: { type: 'dashed', color: '#9ca3af' },
              },
            ],
          },
        },
        ...(avgPrices.length > 0
          ? [{
              name: '均价',
              type: 'line' as const,
              data: avgPrices,
              smooth: false,
              showSymbol: false,
              lineStyle: { color: '#f59e0b', width: 1 },
            }]
          : []),
      ],
    }
  }, [chartData, markLineData, data?.pre_close])

  const volumeOption = useMemo<echarts.EChartsCoreOption>(() => {
    if (!chartData) return {}
    const { volumes, times } = chartData

    return {
      title: { text: '成交量', left: 'center', textStyle: { fontSize: 12 } },
      tooltip: {
        trigger: 'axis',
        formatter: (params: unknown) => {
          const arr = params as Array<{ axisValue: string; value: number; marker: string }>
          if (!arr?.length) return ''
          const v = arr[0].value
          return `${arr[0].axisValue}<br/>${arr[0].marker} 成交量: ${v?.toLocaleString() ?? '-'}手`
        },
      },
      grid: { left: '50px', right: '50px', top: '40px', bottom: '20px' },
      xAxis: {
        type: 'category',
        data: times,
        show: false,
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } },
        axisLabel: { color: '#6b7280' },
      },
      series: [
        {
          name: '成交量',
          type: 'bar',
          data: volumes,
          barWidth: '80%',
          markLine: {
            symbol: 'none',
            silent: true,
            animation: false,
            data: markLineData,
          },
        },
      ],
    }
  }, [chartData, markLineData])

  // 初始化价格图
  useEffect(() => {
    const container = priceContainerRef.current
    if (!container) return
    const instance = echarts.init(container)
    priceChartRef.current = instance
    instance.setOption(priceOption)

    const handleResize = () => instance.resize()
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      instance.dispose()
      priceChartRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const instance = priceChartRef.current
    if (instance) instance.setOption(priceOption, true)
  }, [priceOption])

  // 初始化成交量图
  useEffect(() => {
    const container = volumeContainerRef.current
    if (!container) return
    const instance = echarts.init(container)
    volumeChartRef.current = instance
    instance.setOption(volumeOption)

    const handleResize = () => instance.resize()
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      instance.dispose()
      volumeChartRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const instance = volumeChartRef.current
    if (instance) instance.setOption(volumeOption, true)
  }, [volumeOption])

  if (!data) {
    return (
      <div style={{ background: '#fff', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: 'var(--space-lg)' }}>
        <div style={{ textAlign: 'center', padding: 'var(--space-xl)', color: 'var(--color-gray-400)' }}>
          暂无分时数据
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', gap: 'var(--space-md)', background: '#fff', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: 'var(--space-md)' }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div ref={priceContainerRef} style={{ height: 350, width: '100%' }} />
        <div ref={volumeContainerRef} style={{ height: 180, width: '100%' }} />
      </div>
      <OrderBook orderBook={data.order_book} />
      <TradeTicker ticker={data.tickers} />
    </div>
  )
}
