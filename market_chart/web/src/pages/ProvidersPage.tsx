import { useEffect, useState, useCallback } from 'react'
import { fetchMarketsConfig, saveMarketsConfig, testProviderConnection } from '../api/client.ts'
import type { MarketConfigItem, ProviderConfig } from '../api/client.ts'

export default function ProvidersPage() {
  const [markets, setMarkets] = useState<MarketConfigItem[]>([])
  const [providers, setProviders] = useState<ProviderConfig[]>([])
  const [marketSources, setMarketSources] = useState<Record<string, string>>({})
  const [credentials, setCredentials] = useState<Record<string, Record<string, unknown>>>({})
  const [testStatus, setTestStatus] = useState<Record<string, 'passed' | 'failed'>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'warning' } | null>(null)

  // 加载配置
  useEffect(() => {
    async function load() {
      try {
        const res = await fetchMarketsConfig()
        if (res.status === 'success' && res.data) {
          setMarkets(res.data.markets || [])
          setProviders(res.data.providers || [])
          setMarketSources(res.data.market_sources || {})
          setCredentials(res.data.credentials || {})

          // 初始化测试状态
          const status: Record<string, 'passed' | 'failed'> = {}
          res.data.providers?.forEach((p) => {
            status[p.id] = p.status === 'passed' ? 'passed' : 'failed'
          })
          setTestStatus(status)
        }
      } catch (err) {
        showToast(`加载配置失败: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const showToast = useCallback((message: string, type: 'success' | 'error' | 'warning') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }, [])

  // 选择市场数据源
  const selectMarketSource = useCallback((marketCode: string, providerId: string) => {
    setMarketSources((prev) => ({ ...prev, [marketCode]: providerId }))
  }, [])

  // 保存市场配置
  const handleSaveMarkets = useCallback(async () => {
    setSaving(true)
    try {
      const res = await saveMarketsConfig(marketSources)
      if (res.status === 'success') {
        showToast(`✅ ${res.data?.message || '保存成功'}`, 'success')
      } else {
        showToast(`❌ ${res.message || '保存失败'}`, 'error')
      }
    } catch (err) {
      showToast(`❌ 保存失败: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
    } finally {
      setSaving(false)
    }
  }, [marketSources, showToast])

  // 测试数据源连接
  const handleTestProvider = useCallback(async (providerId: string) => {
    const provider = providers.find((p) => p.id === providerId)
    if (!provider) return

    // 收集凭证输入
    const creds: Record<string, string> = {}
    if (provider.needsConfig) {
      for (const param of provider.params) {
        const input = document.getElementById(`${providerId}_${param.name}`) as HTMLInputElement | null
        if (input?.value) {
          creds[param.name] = input.value
        }
      }
      if (Object.keys(creds).length === 0) {
        showToast('⚠️ 请先填写凭证信息', 'warning')
        return
      }
    }

    setTestingId(providerId)
    try {
      const res = await testProviderConnection(providerId, creds)
      if (res.status === 'success') {
        showToast('✅ 连接测试成功', 'success')
        setTestStatus((prev) => ({ ...prev, [providerId]: 'passed' }))
      } else {
        showToast(`❌ 连接测试失败: ${res.message || '未知错误'}`, 'error')
        setTestStatus((prev) => ({ ...prev, [providerId]: 'failed' }))
      }
    } catch (err) {
      showToast(`❌ 网络错误: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
      setTestStatus((prev) => ({ ...prev, [providerId]: 'failed' }))
    } finally {
      setTestingId(null)
    }
  }, [providers, showToast])

  if (loading) {
    return (
      <div style={{ maxWidth: 1600, margin: '0 auto', padding: 'var(--space-lg)' }}>
        <div className="card text-center text-muted" style={{ padding: 'var(--space-xl)' }}>
          加载配置中...
        </div>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 1600, margin: '0 auto', padding: 'var(--space-lg)' }}>
      {/* Toast 通知 */}
      {toast && (
        <div
          style={{
            position: 'fixed',
            top: 16,
            right: 16,
            zIndex: 1000,
            padding: '12px 20px',
            borderRadius: 'var(--radius-md)',
            fontSize: 'var(--font-size-sm)',
            fontWeight: 500,
            color: '#fff',
            background:
              toast.type === 'success'
                ? 'var(--color-success)'
                : toast.type === 'warning'
                  ? 'var(--color-warning)'
                  : 'var(--color-danger)',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          }}
        >
          {toast.message}
        </div>
      )}

      <h1 style={{ fontSize: 'var(--font-size-xl)', marginBottom: 'var(--space-lg)', color: 'var(--color-gray-800)' }}>
        市场数据源配置
      </h1>

      {/* 上栏：市场配置 */}
      <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: 'var(--space-md) var(--space-lg)',
            borderBottom: '1px solid var(--color-border)',
            fontWeight: 600,
            fontSize: 'var(--font-size-lg)',
            color: 'var(--color-gray-700)',
          }}
        >
          <span>市场配置</span>
          <button
            className="btn btn-primary"
            onClick={handleSaveMarkets}
            disabled={saving}
            style={{ opacity: saving ? 0.7 : 1 }}
          >
            {saving ? '💾 保存中...' : '💾 保存'}
          </button>
        </div>
        <div>
          {markets.map((m) => {
            const supported = providers.filter((p) => p.markets.includes(m.code))
            return (
              <div
                key={m.code}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '200px 1fr',
                  gap: 20,
                  padding: 'var(--space-md) var(--space-lg)',
                  borderBottom: '1px solid var(--color-gray-100)',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLDivElement).style.backgroundColor = 'var(--color-gray-50)'
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLDivElement).style.backgroundColor = 'transparent'
                }}
              >
                <div style={{ fontWeight: 600, paddingTop: 8, color: 'var(--color-gray-700)' }}>
                  {m.icon} {m.name}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
                  {supported.map((p) => {
                    const isEnabled = testStatus[p.id] === 'passed'
                    const isChecked = marketSources[m.code] === p.id
                    return (
                      <label
                        key={p.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          padding: '8px 12px',
                          borderRadius: 'var(--radius-sm)',
                          whiteSpace: 'nowrap',
                          cursor: isEnabled ? 'pointer' : 'not-allowed',
                          opacity: isEnabled ? 1 : 0.5,
                          transition: 'background 0.15s',
                        }}
                        onMouseEnter={(e) => {
                          if (isEnabled) (e.currentTarget as HTMLLabelElement).style.backgroundColor = 'var(--color-gray-100)'
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLLabelElement).style.backgroundColor = 'transparent'
                        }}
                      >
                        <input
                          type="radio"
                          name={`market_${m.code}`}
                          value={p.id}
                          checked={isChecked}
                          disabled={!isEnabled}
                          onChange={() => selectMarketSource(m.code, p.id)}
                          style={{ width: 18, height: 18, cursor: isEnabled ? 'pointer' : 'not-allowed' }}
                        />
                        <span style={{ color: 'var(--color-gray-700)' }}>
                          {p.name}
                          {isEnabled ? (
                            <span style={{ color: 'var(--color-success)', marginLeft: 4 }}>✓</span>
                          ) : (
                            <span style={{ color: 'var(--color-danger)', marginLeft: 4 }}>✗</span>
                          )}
                        </span>
                      </label>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* 下栏：数据源配置 */}
      <div className="card">
        <div
          style={{
            padding: 'var(--space-md) var(--space-lg)',
            borderBottom: '1px solid var(--color-border)',
            fontWeight: 600,
            fontSize: 'var(--font-size-lg)',
            color: 'var(--color-gray-700)',
          }}
        >
          数据源配置
        </div>
        <div>
          {providers.map((p) => {
            const isPassed = testStatus[p.id] === 'passed'
            const statusText = isPassed ? '✅ 通过' : '❌ 未通过'
            const statusBg = isPassed ? '#d1fae5' : '#fee2e2'
            const statusColor = isPassed ? '#065f46' : '#991b1b'

            return (
              <div
                key={p.id}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '200px 1fr 200px',
                  gap: 20,
                  padding: 'var(--space-md) var(--space-lg)',
                  borderBottom: '1px solid var(--color-gray-100)',
                  alignItems: 'center',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLDivElement).style.backgroundColor = 'var(--color-gray-50)'
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLDivElement).style.backgroundColor = 'transparent'
                }}
              >
                <div style={{ fontWeight: 600, color: 'var(--color-gray-800)' }}>{p.name}</div>
                <div>
                  {p.needsConfig ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {p.params.map((param) => (
                        <div key={param.name} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                          <label style={{ minWidth: 100, fontSize: 13, color: 'var(--color-gray-600)' }}>
                            {param.label}:
                          </label>
                          <input
                            id={`${p.id}_${param.name}`}
                            type={param.type}
                            className="form-control"
                            placeholder={param.placeholder}
                            defaultValue={
                              (credentials[p.id]?.[param.name] as string) || ''
                            }
                            style={{ flex: 1 }}
                          />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ color: 'var(--color-success)', fontSize: 14 }}>✓ 免配置</div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'flex-end' }}>
                  <span
                    style={{
                      padding: '4px 8px',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: 12,
                      fontWeight: 500,
                      whiteSpace: 'nowrap',
                      background: statusBg,
                      color: statusColor,
                    }}
                  >
                    {statusText}
                  </span>
                  <button
                    className="btn btn-secondary"
                    onClick={() => handleTestProvider(p.id)}
                    disabled={testingId === p.id}
                    style={{ fontSize: 'var(--font-size-sm)', opacity: testingId === p.id ? 0.7 : 1 }}
                  >
                    {testingId === p.id ? '🔄 测试中...' : p.needsConfig ? '🔌 测试并保存' : '🔌 测试'}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
