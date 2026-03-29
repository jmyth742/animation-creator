import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    console.error('ErrorBoundary caught:', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
          <div className="bg-zinc-900 border-2 border-red-700 p-8 text-center max-w-md"
            style={{ boxShadow: '4px 4px 0 0 #000' }}>
            <div className="text-4xl mb-4">💥</div>
            <h2 className="font-pixel text-red-400 mb-3" style={{ fontSize: '10px' }}>
              SOMETHING CRASHED
            </h2>
            <p className="text-sm text-zinc-400 mb-2 font-mono break-all">
              {this.state.error?.message || 'Unknown error'}
            </p>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null })
                window.location.reload()
              }}
              className="mt-4 px-4 py-2 bg-accent-600 text-white font-pixel text-xs border-2 border-accent-400 hover:bg-accent-500"
              style={{ boxShadow: '2px 2px 0 0 #000' }}
            >
              RELOAD
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
