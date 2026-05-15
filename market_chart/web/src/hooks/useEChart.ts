import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

export function useEChart(
  option: echarts.EChartsCoreOption,
  onInit?: (instance: echarts.ECharts) => void
) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const instance = echarts.init(container)
    chartRef.current = instance
    instance.setOption(option)
    onInit?.(instance)

    const handleResize = () => instance.resize()
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      instance.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    const instance = chartRef.current
    if (instance) {
      instance.setOption(option, true)
    }
  }, [option])

  return { containerRef, chartRef }
}
