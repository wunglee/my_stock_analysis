import { NavLink } from 'react-router-dom'

const navItems = [
  { path: '/explorer', label: 'Explorer' },
  { path: '/providers', label: 'Providers' },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div>
      <header
        style={{
          background: 'var(--color-bg-dark)',
          color: '#fff',
          boxShadow: 'var(--shadow-md)',
          position: 'sticky',
          top: 0,
          zIndex: 1000,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            maxWidth: 1600,
            margin: '0 auto',
            padding: '0 var(--space-lg)',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-md)',
              padding: 'var(--space-md) 0',
            }}
          >
            <NavLink
              to="/"
              style={{
                fontSize: 'var(--font-size-xl)',
                fontWeight: 700,
                color: '#fff',
                textDecoration: 'none',
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-sm)',
              }}
            >
              <span>📊</span> DeepSeekQuant
            </NavLink>
          </div>
          <nav style={{ display: 'flex', gap: 'var(--space-xs)' }}>
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                style={({ isActive }) => ({
                  padding: 'var(--space-md) var(--space-lg)',
                  color: isActive ? '#fff' : 'rgba(255, 255, 255, 0.8)',
                  textDecoration: 'none',
                  borderRadius: 'var(--radius-sm)',
                  transition: 'all 0.2s',
                  fontSize: 'var(--font-size-sm)',
                  fontWeight: 500,
                  background: isActive
                    ? 'var(--color-primary)'
                    : 'transparent',
                })}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-sm)',
              padding: 'var(--space-sm) var(--space-md)',
              background: 'rgba(255, 255, 255, 0.1)',
              borderRadius: 'var(--radius-sm)',
              fontSize: 'var(--font-size-xs)',
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: 'var(--color-success)',
                animation: 'pulse 2s infinite',
              }}
            />
            <span>系统运行中</span>
          </div>
        </div>
      </header>
      <main>{children}</main>
    </div>
  )
}
