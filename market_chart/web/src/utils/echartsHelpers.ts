import type { EChartsType } from 'echarts'

/**
 * 显示图表空状态
 */
export function showChartEmpty(chart: EChartsType, text = '暂无数据'): void {
  chart.setOption(
    {
      xAxis: { show: false },
      yAxis: { show: false },
      series: [],
      graphic: [
        {
          type: 'text',
          left: 'center',
          top: 'center',
          style: {
            text,
            fontSize: 16,
            fill: '#999',
          },
        },
      ],
    },
    true
  )
}

/**
 * 显示/隐藏图表加载状态
 */
export function showChartLoading(chart: EChartsType, show: boolean, text = '加载中...'): void {
  if (show) {
    chart.showLoading({
      text,
      color: '#2563eb',
      textColor: '#666',
      maskColor: 'rgba(255, 255, 255, 0.8)',
    })
  } else {
    chart.hideLoading()
  }
}
