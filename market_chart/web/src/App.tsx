import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout.tsx'
import ErrorBoundary from './components/ErrorBoundary.tsx'
import ExplorerPage from './pages/ExplorerPage.tsx'

const ProvidersPage = lazy(() => import('./pages/ProvidersPage.tsx'))

function App() {
  return (
    <Layout>
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<ExplorerPage />} />
          <Route path="/explorer" element={<ExplorerPage />} />
          <Route
            path="/providers"
            element={
              <Suspense
                fallback={
                  <div className="card text-center text-muted" style={{ margin: 'var(--space-lg)' }}>
                    加载中...
                  </div>
                }
              >
                <ProvidersPage />
              </Suspense>
            }
          />
        </Routes>
      </ErrorBoundary>
    </Layout>
  )
}

export default App
