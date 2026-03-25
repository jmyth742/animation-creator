import React, { useEffect, useState } from 'react'
import { X, Sparkles, ArrowLeft } from 'lucide-react'
import { get, post } from '../api/client'

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="label-pixel">{label}</label>
      {hint && <p className="text-retro text-zinc-500 mb-1" style={{ fontSize: '15px' }}>{hint}</p>}
      {children}
    </div>
  )
}

const GENRE_COLORS = {
  'Film Noir': 'text-amber-400 border-amber-700 bg-amber-900/20',
  'Sci-Fi': 'text-cyan-400 border-cyan-700 bg-cyan-900/20',
  'Folk Horror': 'text-emerald-400 border-emerald-700 bg-emerald-900/20',
}

function TemplateCard({ template, onSelect }) {
  const colorClass = GENRE_COLORS[template.genre] || 'text-zinc-400 border-zinc-600 bg-zinc-800'

  return (
    <button
      onClick={() => onSelect(template)}
      className="text-left bg-zinc-800 border-2 border-zinc-700 p-4 hover:border-accent-500 transition-colors group"
      style={{ boxShadow: '2px 2px 0 0 #000' }}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className={`font-pixel px-1.5 py-0.5 border ${colorClass}`} style={{ fontSize: '5px' }}>
          {template.genre}
        </span>
      </div>
      <h3 className="font-pixel text-zinc-100 mb-1 group-hover:text-accent-400 transition-colors" style={{ fontSize: '8px' }}>
        {template.title}
      </h3>
      <p className="text-retro text-zinc-500 line-clamp-2 mb-2" style={{ fontSize: '14px' }}>
        {template.description}
      </p>
      <div className="flex items-center gap-3">
        <span className="font-pixel text-zinc-600" style={{ fontSize: '5px' }}>
          {template.character_count} CHAR{template.character_count !== 1 ? 'S' : ''}
        </span>
        <span className="font-pixel text-zinc-600" style={{ fontSize: '5px' }}>
          {template.location_count} LOC{template.location_count !== 1 ? 'S' : ''}
        </span>
      </div>
    </button>
  )
}

export default function NewProjectModal({ onCreated, onClose }) {
  const [mode, setMode] = useState('choose') // 'choose' | 'blank' | 'template-loading'
  const [form, setForm] = useState({ title: '', premise: '', tone: '', visual_style: '', setting: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [templates, setTemplates] = useState([])
  const [templatesLoading, setTemplatesLoading] = useState(true)

  useEffect(() => {
    const fetchTemplates = async () => {
      try {
        const data = await get('/projects/templates')
        setTemplates(data)
      } catch {
        setTemplates([])
      } finally {
        setTemplatesLoading(false)
      }
    }
    fetchTemplates()
  }, [])

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

  const handleTemplateSelect = async (template) => {
    setMode('template-loading')
    setError('')
    try {
      const project = await post(`/projects/from-template?template_id=${template.id}`)
      onCreated(project)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create from template.')
      setMode('choose')
    }
  }

  // Choose mode — template gallery + blank option
  if (mode === 'choose') {
    return (
      <div className="modal-overlay">
        <div className="modal-pixel max-w-lg">
          <div className="modal-header">
            <div className="flex items-center gap-3">
              <span className="text-2xl">🎬</span>
              <span className="heading-pixel-sm text-accent-400">NEW STORY PROJECT</span>
            </div>
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 text-lg font-pixel p-1">
              ✕
            </button>
          </div>

          <div className="px-6 py-5 space-y-5 overflow-y-auto" style={{ maxHeight: '70vh' }}>
            {error && <div className="alert-error">✖ {error}</div>}

            {/* Templates */}
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="w-3 h-3 text-accent-400" />
                <span className="font-pixel text-zinc-300" style={{ fontSize: '7px' }}>START FROM TEMPLATE</span>
              </div>
              {templatesLoading ? (
                <div className="flex items-center justify-center py-6 gap-3">
                  <span className="pixel-spinner" />
                  <span className="text-retro text-zinc-500">LOADING TEMPLATES...</span>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-3">
                  {templates.map((t) => (
                    <TemplateCard key={t.id} template={t} onSelect={handleTemplateSelect} />
                  ))}
                </div>
              )}
            </div>

            {/* Divider */}
            <div className="flex items-center gap-3">
              <div className="flex-1 border-t border-zinc-700" />
              <span className="font-pixel text-zinc-600" style={{ fontSize: '6px' }}>OR</span>
              <div className="flex-1 border-t border-zinc-700" />
            </div>

            {/* Blank project */}
            <button
              onClick={() => setMode('blank')}
              className="w-full text-left bg-zinc-800 border-2 border-dashed border-zinc-600 p-4 hover:border-accent-500 transition-colors"
              style={{ boxShadow: '2px 2px 0 0 #000' }}
            >
              <h3 className="font-pixel text-zinc-300 mb-1" style={{ fontSize: '8px' }}>
                BLANK PROJECT
              </h3>
              <p className="text-retro text-zinc-600" style={{ fontSize: '14px' }}>
                Start from scratch with your own concept.
              </p>
            </button>
          </div>

          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t-2 border-zinc-700">
            <button type="button" onClick={onClose} className="btn-pixel-ghost">
              CANCEL
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Template loading state
  if (mode === 'template-loading') {
    return (
      <div className="modal-overlay">
        <div className="modal-pixel max-w-sm">
          <div className="px-6 py-12 text-center">
            <span className="pixel-spinner mb-4 mx-auto" />
            <p className="text-retro text-zinc-400">CREATING FROM TEMPLATE...</p>
          </div>
        </div>
      </div>
    )
  }

  // Blank project form
  return (
    <div className="modal-overlay">
      <div className="modal-pixel max-w-lg">

        {/* Header */}
        <div className="modal-header">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMode('choose')}
              className="text-zinc-500 hover:text-zinc-200 p-1"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
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
