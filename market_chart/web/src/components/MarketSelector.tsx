import type { MarketConfig } from '../types'

interface MarketSelectorProps {
  markets: MarketConfig[]
  selected: string
  onSelect: (code: string) => void
}

export default function MarketSelector({ markets, selected, onSelect }: MarketSelectorProps) {
  return (
    <div className="segmented-control" style={{ marginBottom: 'var(--space-md)' }}>
      {markets.map((market) => (
        <button
          key={market.code}
          className={`btn-segment ${selected === market.code ? 'active' : ''}`}
          onClick={() => onSelect(market.code)}
        >
          {market.icon} {market.name}
        </button>
      ))}
    </div>
  )
}
