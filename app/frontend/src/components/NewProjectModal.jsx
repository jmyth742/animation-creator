import React, { useState } from 'react'
import { X } from 'lucide-react'
import { post } from '../api/client'

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="label-pixel">{label}</label>
      {hint && <p className="text-retro text-zinc-500 mb-1" style={{ fontSize: '15px' }}>{hint}</p>}
      {children}
    </div>
  )
}

export default function NewProjectModal({ onCreated, onClose }) {
  const [form, setForm] = useState({ title: '', premise: '', tone: '', visual_style: '', setting: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleChange = (e) => setForm((f) => ({ ...f, [e.target.name]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.title.trim()) { setError('Title is required.'); return }
    if (!form.premise.trim()) { setError('Premise is required.'); return }
    setError('')
    setLoading(true)
    try {
      const project = await post('/projects', form)
      onCreated(project)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create project.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-pixel max-w-lg">

        {/* Header */}
        <div className="modal-header">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🎬</span>
            <span className="heading-pixel-sm text-accent-400">NEW STORY PROJECT</span>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 text-lg font-pixel p-1">
            ✕
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {error && <div className="alert-error">✖ {error}</div>}

          <Field label="TITLE *">
            <input
              name="title"
              value={form.title}
              onChange={handleChange}
              required
              className="input-pixel"
              placeholder="My Amazing Series"
              autoFocus
            />
          </Field>

          <Field label="PREMISE *" hint="What is this series about?">
            <textarea
              name="premise"
              value={form.premise}
              onChange={handleChange}
              required
              rows={3}
              className="input-pixel resize-none"
              placeholder="A gripping drama set in..."
            />
          </Field>

          <Field label="TONE">
            <input
              name="tone"
              value={form.tone}
              onChange={handleChange}
              className="input-pixel"
              placeholder="e.g. dark comedy, heartfelt drama"
            />
          </Field>

          <Field label="VISUAL STYLE" hint="Art style for AI video generation">
            <textarea
              name="visual_style"
              value={form.visual_style}
              onChange={handleChange}
              rows={2}
              className="input-pixel resize-none"
              placeholder="Cinematic, film grain, moody lighting..."
            />
          </Field>

          <Field label="SETTING" hint="Where and when is this set?">
            <textarea
              name="setting"
              value={form.setting}
              onChange={handleChange}
              rows={2}
              className="input-pixel resize-none"
              placeholder="Belfast, Northern Ireland, 1990s"
            />
          </Field>
        </form>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t-2 border-zinc-700">
          <button type="button" onClick={onClose} className="btn-pixel-ghost">
            CANCEL
          </button>
          <button onClick={handleSubmit} disabled={loading} className="btn-pixel">
            {loading ? '▶▶ CREATING...' : '▶ CREATE PROJECT'}
          </button>
        </div>
      </div>
    </div>
  )
}
