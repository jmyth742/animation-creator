import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const login = useAuthStore((s) => s.login)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid email or password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="scanlines min-h-screen bg-zinc-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="flex flex-col items-center mb-10 text-center">
          <div className="text-6xl mb-4">👾</div>
          <h1 className="heading-pixel-lg text-accent-400 mb-2">STORY BUILDER</h1>
          <p className="text-retro text-zinc-400">INSERT COIN TO CONTINUE</p>
        </div>

        {/* Panel */}
        <div className="pixel-panel p-6">
          <div className="heading-pixel-sm text-accent-500 mb-6 border-b-2 border-zinc-700 pb-3">
            ▶ PLAYER LOGIN
          </div>

          {error && (
            <div className="alert-error mb-4">
              ✖ {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="label-pixel">EMAIL ADDRESS</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                className="input-pixel"
                placeholder="player@example.com"
              />
            </div>

            <div>
              <label className="label-pixel">PASSWORD</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="input-pixel"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-pixel w-full justify-center mt-2"
            >
              {loading ? '▶▶ LOADING...' : '▶ PRESS START'}
            </button>
          </form>
        </div>

        <p className="text-center text-retro text-zinc-500 mt-6">
          NEW PLAYER?{' '}
          <Link to="/register" className="text-accent-400 hover:text-accent-300">
            CREATE ACCOUNT
          </Link>
        </p>
      </div>
    </div>
  )
}
