import { useState } from 'react'
import type { StockItem } from '../types'

interface StockListProps {
  items: StockItem[]
  selected: string | null
  onSelect: (id: string) => void
  onRemove: (id: string) => void
  onAdd: (id: string, name: string) => void
}

export default function StockList({ items, selected, onSelect, onRemove, onAdd }: StockListProps) {
  const [showModal, setShowModal] = useState(false)
  const [newId, setNewId] = useState('')
  const [newName, setNewName] = useState('')

  const handleAdd = () => {
    if (newId.trim() && newName.trim()) {
      onAdd(newId.trim(), newName.trim())
      setNewId('')
      setNewName('')
      setShowModal(false)
    }
  }

  return (
    <div
      style={{
        background: '#fff',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-md)',
        width: 280,
        flexShrink: 0,
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 'var(--space-md)',
          fontWeight: 600,
          color: 'var(--color-gray-700)',
          fontSize: 'var(--font-size-sm)',
        }}
      >
        <span>市场主要指数/股票</span>
        <button
          onClick={() => setShowModal(true)}
          style={{
            padding: '4px 10px',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--color-gray-50)',
            color: 'var(--color-gray-600)',
            fontSize: 'var(--font-size-xs)',
            cursor: 'pointer',
          }}
        >
          + 添加
        </button>
      </div>

      <div style={{ maxHeight: 500, overflowY: 'auto' }}>
        {items.length === 0 && (
          <div style={{ textAlign: 'center', padding: 'var(--space-xl)', color: 'var(--color-gray-400)', fontSize: 'var(--font-size-sm)' }}>
            暂无数据
          </div>
        )}
        {items.map((item) => (
          <div
            key={item.id}
            onClick={() => onSelect(item.id)}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '10px 12px',
              borderBottom: '1px solid var(--color-gray-100)',
              cursor: 'pointer',
              transition: 'background 0.2s',
              background: selected === item.id ? '#eff6ff' : 'transparent',
              borderLeft: selected === item.id ? '3px solid var(--color-primary)' : '3px solid transparent',
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1 }}>
              <span style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500, color: 'var(--color-gray-800)' }}>
                {item.name}
              </span>
              <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-gray-500)' }}>
                {item.id}
              </span>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation()
                onRemove(item.id)
              }}
              style={{
                padding: '4px 8px',
                border: 'none',
                background: 'transparent',
                color: 'var(--color-gray-400)',
                fontSize: 'var(--font-size-xs)',
                cursor: 'pointer',
              }}
              title="删除"
            >
              ×
            </button>
          </div>
        ))}
      </div>

      {showModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
          }}
          onClick={() => setShowModal(false)}
        >
          <div
            style={{
              background: '#fff',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-xl)',
              width: '90%',
              maxWidth: 400,
              boxShadow: '0 10px 25px rgba(0,0,0,0.2)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, marginBottom: 'var(--space-lg)', color: 'var(--color-gray-800)' }}>
              添加股票/指数
            </div>
            <div style={{ marginBottom: 'var(--space-md)' }}>
              <label style={{ display: 'block', marginBottom: 'var(--space-sm)', fontWeight: 500, color: 'var(--color-gray-700)', fontSize: 'var(--font-size-sm)' }}>
                代码
              </label>
              <input
                value={newId}
                onChange={(e) => setNewId(e.target.value)}
                placeholder="如: 000001.SH"
                style={{
                  width: '100%',
                  padding: 'var(--space-sm)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 'var(--font-size-base)',
                }}
              />
            </div>
            <div style={{ marginBottom: 'var(--space-lg)' }}>
              <label style={{ display: 'block', marginBottom: 'var(--space-sm)', fontWeight: 500, color: 'var(--color-gray-700)', fontSize: 'var(--font-size-sm)' }}>
                名称
              </label>
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="如: 上证指数"
                style={{
                  width: '100%',
                  padding: 'var(--space-sm)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 'var(--font-size-base)',
                }}
              />
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-sm)', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setShowModal(false)}
                style={{
                  padding: 'var(--space-sm) var(--space-lg)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-sm)',
                  background: '#fff',
                  color: 'var(--color-gray-600)',
                  cursor: 'pointer',
                  fontSize: 'var(--font-size-sm)',
                }}
              >
                取消
              </button>
              <button
                onClick={handleAdd}
                style={{
                  padding: 'var(--space-sm) var(--space-lg)',
                  border: '1px solid var(--color-primary)',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--color-primary)',
                  color: '#fff',
                  cursor: 'pointer',
                  fontSize: 'var(--font-size-sm)',
                }}
              >
                添加
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
