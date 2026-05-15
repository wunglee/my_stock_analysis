import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div className="card text-center" style={{ margin: 'var(--space-lg)', color: 'var(--color-danger)' }}>
            <div style={{ fontSize: 'var(--font-size-xl)', marginBottom: 'var(--space-md)' }}>出错了</div>
            <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-gray-500)' }}>
              {this.state.error?.message || '未知错误'}
            </div>
          </div>
        )
      )
    }
    return this.props.children
  }
}
