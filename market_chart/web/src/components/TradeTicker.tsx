import type { TickerData } from '../types'

interface TradeTickerProps {
  ticker?: TickerData
}

export default function TradeTicker({ ticker }: TradeTickerProps) {
  if (!ticker || ticker.message) {
    return (
      <div style={{ width: 200, flexShrink: 0, padding: 'var(--space-md)' }}>
        <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-md)', color: 'var(--color-gray-700)' }}>
          成交记录
        </div>
        <div style={{ textAlign: 'center', color: 'var(--color-gray-400)', fontSize: 'var(--font-size-xs)' }}>
          {ticker?.message || '暂无数据'}
        </div>
      </div>
    )
  }

  const items = ticker.items || []

  return (
    <div style={{ width: 200, flexShrink: 0, padding: 'var(--space-md)' }}>
      <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-md)', color: 'var(--color-gray-700)' }}>
        成交记录
      </div>
      <div style={{ maxHeight: 400, overflowY: 'auto', fontSize: 'var(--font-size-xs)' }}>
        <div style={{ display: 'flex', gap: 4, marginBottom: 4, color: 'var(--color-gray-500)' }}>
          <span style={{ flex: 1 }}>时间</span>
          <span style={{ flex: 1 }}>价格</span>
          <span style={{ flex: 1, textAlign: 'right' }}>量</span>
        </div>
        {items.map((item, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              gap: 4,
              padding: '2px 0',
              color: item.type === 'buy' ? 'var(--color-success)' : 'var(--color-danger)',
            }}
          >
            <span style={{ flex: 1 }}>{item.time.slice(0, 5)}</span>
            <span style={{ flex: 1 }}>{item.price.toFixed(2)}</span>
            <span style={{ flex: 1, textAlign: 'right' }}>{item.volume}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
