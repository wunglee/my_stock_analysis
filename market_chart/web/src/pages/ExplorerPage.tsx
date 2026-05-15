import { useExplorer } from '../hooks/useExplorer.ts'
import MarketSelector from '../components/MarketSelector.tsx'
import StockList from '../components/StockList.tsx'
import SymbolPanel from '../components/SymbolPanel.tsx'

export default function ExplorerPage() {
  const {
    markets,
    selectedMarket,
    currentMarket,
    marketsLoading,
    marketsError,
    selectMarket,
    allStocks,
    selectedStock,
    currentSymbolObj,
    handleSelectStock,
    handleRemoveStock,
    handleAddStock,
  } = useExplorer()

  return (
    <div style={{ maxWidth: 1600, margin: '0 auto', padding: 'var(--space-lg)' }}>
      {/* 市场头部信息 */}
      <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 style={{ margin: '0 0 var(--space-sm) 0', fontSize: 'var(--font-size-xl)', color: 'var(--color-gray-800)' }}>
              {currentMarket ? `${currentMarket.icon} ${currentMarket.name}` : '选择市场'}
            </h2>
            {currentMarket && (
              <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-gray-500)' }}>
                <span>交易时间：{currentMarket.trading_hours}</span>
                {currentMarket.detailed_trading_hours?.pre_market && (
                  <>
                    <span style={{ margin: '0 var(--space-md)' }}>|</span>
                    <span>盘前交易：{currentMarket.detailed_trading_hours.pre_market}</span>
                  </>
                )}
              </div>
            )}
          </div>
          <div style={{ fontSize: 32 }}>{currentMarket?.icon ?? '🌐'}</div>
        </div>
      </div>

      {/* 市场选择器 */}
      {marketsLoading ? (
        <div className="text-muted" style={{ marginBottom: 'var(--space-md)' }}>加载市场中...</div>
      ) : marketsError ? (
        <div style={{ marginBottom: 'var(--space-md)', color: 'var(--color-danger)' }}>加载失败: {marketsError}</div>
      ) : (
        <MarketSelector markets={markets} selected={selectedMarket} onSelect={selectMarket} />
      )}

      {/* 左右分栏：股票列表 + 个股面板 */}
      <div style={{ display: 'flex', gap: 'var(--space-lg)', alignItems: 'flex-start' }}>
        {/* 左侧：股票列表 */}
        <StockList
          items={allStocks}
          selected={selectedStock}
          onSelect={handleSelectStock}
          onRemove={handleRemoveStock}
          onAdd={handleAddStock}
        />

        {/* 右侧：个股面板（模式、图表类型、图表 全部在里面） */}
        <SymbolPanel
          symbolObj={currentSymbolObj}
          marketCode={selectedMarket}
        />
      </div>
    </div>
  )
}
