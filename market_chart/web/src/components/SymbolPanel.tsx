import { useState, useEffect, useRef } from 'react'
import type { DataMode, TradingPhase } from '../types'

declare global {
  interface Window {
    IntradayChart?: {
      setCurrent: (symbol: unknown, isStock: boolean, marketCode: string, useMockMode: boolean, mockTradingPhase: string) => void
      stopIntradayUpdateTimer: () => void
    }
    KlineChart?: {
      setCurrent: (symbol: unknown, marketCode: string, useMockMode: boolean, mockTradingPhase?: string) => void
      stopRealtimeKlineUpdateTimer: () => void
      showEmpty?: (text?: string) => void
      selectPeriod: (period: string, element: HTMLElement) => void
      selectIndicator: (indicator: string, element: HTMLElement) => void
      toggleChipPanel: () => void
      setRealtimeUpdateEnabled: (enabled: boolean) => void
    }
  }
}

const PHASE_LABELS: Record<TradingPhase, string> = {
  before_open: '盘前',
  trading: '盘中',
  after_close: '盘后',
}

const CHART_LABELS: Record<string, string> = {
  intraday: '分时图',
  kline: 'K线图',
}

interface SymbolPanelProps {
  symbolObj: { id: string; name: string; type?: string } | null
  marketCode: string
}

export default function SymbolPanel({ symbolObj, marketCode }: SymbolPanelProps) {
  const [mode, setMode] = useState<DataMode>('real')
  const [phase, setPhase] = useState<TradingPhase>('trading')
  const [chartType, setChartType] = useState<'intraday' | 'kline'>('intraday')

  // 保存上一个 symbol，用于判断是否需要重新初始化图表
  const prevSymbolRef = useRef(symbolObj?.id)
  const prevModeRef = useRef(mode)
  const prevPhaseRef = useRef(phase)

  const isIndex = symbolObj?.type === 'index'
  const symbol = symbolObj

  // 当股票切换时，调用原始 JS 图表组件的 setCurrent
  useEffect(() => {
    if (!symbol || !marketCode) return

    const isMock = mode === 'mock'

    if (chartType === 'intraday') {
      // 初始化分时图
      if (window.IntradayChart) {
        window.IntradayChart.setCurrent(symbol, !isIndex, marketCode, isMock, phase)
      }
    } else {
      // 初始化K线图
      if (window.KlineChart) {
        window.KlineChart.setCurrent(symbol, marketCode, isMock, phase)
      }
    }

    prevSymbolRef.current = symbol.id
    prevModeRef.current = mode
    prevPhaseRef.current = phase

    return () => {
      if (window.KlineChart) window.KlineChart.stopRealtimeKlineUpdateTimer()
      if (window.IntradayChart) window.IntradayChart.stopIntradayUpdateTimer()
    }
  }, [symbol, marketCode, chartType, isIndex, mode, phase])

  // 当模式或阶段变化时，重新加载数据
  useEffect(() => {
    if (!symbol || !marketCode) return
    if (prevModeRef.current === mode && prevPhaseRef.current === phase && prevSymbolRef.current === symbol.id) return

    const isMock = mode === 'mock'

    if (chartType === 'intraday' && window.IntradayChart) {
      window.IntradayChart.setCurrent(symbol, !isIndex, marketCode, isMock, phase)
    } else if (chartType === 'kline' && window.KlineChart) {
      window.KlineChart.setCurrent(symbol, marketCode, isMock, phase)
    }

    prevModeRef.current = mode
    prevPhaseRef.current = phase
  }, [mode, phase, symbol, marketCode, chartType, isIndex])

  if (!symbol) {
    return (
      <div style={{ flex: 1, minWidth: 0 }} className="card text-center text-muted">
        请选择股票/指数查看详情
      </div>
    )
  }

  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      {/* 个股面板内：模式选择 + 阶段选择 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-md)', marginBottom: 'var(--space-md)' }}>
        <div className="segmented-control">
          {(['real', 'mock'] as const).map((m) => (
            <button
              key={m}
              className={`btn-segment ${mode === m ? 'active' : ''}`}
              onClick={() => setMode(m)}
            >
              {m === 'real' ? '真实数据' : '模拟数据'}
            </button>
          ))}
        </div>

        {mode === 'mock' && (
          <div className="segmented-control">
            {(['before_open', 'trading', 'after_close'] as const).map((p) => (
              <button
                key={p}
                className={`btn-segment ${phase === p ? 'active' : ''}`}
                onClick={() => setPhase(p)}
                style={{
                  background: phase === p ? 'var(--color-warning)' : undefined,
                  borderColor: phase === p ? 'var(--color-warning)' : undefined,
                }}
              >
                {PHASE_LABELS[p]}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 个股面板内：图表类型选择 */}
      <div style={{ display: 'flex', gap: 'var(--space-md)', marginBottom: 'var(--space-md)', alignItems: 'center' }}>
        <div className="segmented-control">
          {(['intraday', 'kline'] as const).map((t) => (
            <button
              key={t}
              className={`btn-segment ${chartType === t ? 'active' : ''}`}
              onClick={() => setChartType(t)}
            >
              {CHART_LABELS[t]}
            </button>
          ))}
        </div>
      </div>

      {/* 图表容器区域 - 同时渲染两个容器供原始JS组件操作 */}
      <div id="klineContainer" style={{ display: chartType === 'kline' ? 'block' : 'none' }} />
      <div id="intradayContainer" style={{ display: chartType === 'intraday' ? 'flex' : 'none', width: '100%', minHeight: 450 }} />
    </div>
  )
}
