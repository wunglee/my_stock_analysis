declare global {
  interface Window {
    echarts: typeof import('echarts')
    KlineChart: {
      setCurrent: (symbol: { id: string; name?: string }, marketCode: string, useMockMode: boolean, mockTradingPhase?: string) => void
      showEmpty: (text?: string) => void
      stopRealtimeKlineUpdateTimer: () => void
      selectPeriod: (period: string, element: HTMLElement) => void
      selectIndicator: (indicator: string, element: HTMLElement) => void
      toggleChipPanel: () => void
      setRealtimeUpdateEnabled: (enabled: boolean) => void
    }
  }
}

export {}
