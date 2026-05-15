import type { OrderBook as OrderBookType } from '../types'

interface OrderBookProps {
  orderBook?: OrderBookType
}

export default function OrderBook({ orderBook }: OrderBookProps) {
  if (!orderBook || orderBook.message) {
    return (
      <div style={{ width: 180, flexShrink: 0, padding: 'var(--space-md)' }}>
        <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-md)', color: 'var(--color-gray-700)' }}>
          盘口
        </div>
        <div style={{ textAlign: 'center', color: 'var(--color-gray-400)', fontSize: 'var(--font-size-xs)' }}>
          {orderBook?.message || '暂无数据'}
        </div>
      </div>
    )
  }

  const asks = [...(orderBook.asks || [])].reverse()
  const bids = orderBook.bids || []

  return (
    <div style={{ width: 180, flexShrink: 0, padding: 'var(--space-md)' }}>
      <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 'var(--space-md)', color: 'var(--color-gray-700)' }}>
        盘口
      </div>
      <div style={{ fontSize: 'var(--font-size-xs)' }}>
        <div style={{ display: 'flex', gap: 4, marginBottom: 4, color: 'var(--color-gray-500)' }}>
          <span style={{ flex: 1 }}>卖价</span>
          <span style={{ flex: 1, textAlign: 'right' }}>量</span>
        </div>
        {asks.map((ask, i) => (
          <div key={`ask-${i}`} style={{ display: 'flex', gap: 4, padding: '2px 0', color: 'var(--color-danger)' }}>
            <span style={{ flex: 1 }}>{ask.price.toFixed(2)}</span>
            <span style={{ flex: 1, textAlign: 'right' }}>{ask.volume}</span>
          </div>
        ))}
        <div style={{ borderTop: '1px solid var(--color-border)', margin: 'var(--space-sm) 0' }} />
        {bids.map((bid, i) => (
          <div key={`bid-${i}`} style={{ display: 'flex', gap: 4, padding: '2px 0', color: 'var(--color-success)' }}>
            <span style={{ flex: 1 }}>{bid.price.toFixed(2)}</span>
            <span style={{ flex: 1, textAlign: 'right' }}>{bid.volume}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
