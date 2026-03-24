import React, { useState } from 'react'
import { X, Wand2, Check, Star } from 'lucide-react'
import { post, put } from '../api/client'

const VOICES = [
  { value: 'en-GB-RyanNeural',    label: 'Ryan — British Male' },
  { value: 'en-GB-ThomasNeural',  label: 'Thomas — British Male' },
  { value: 'en-GB-SoniaNeural',   label: 'Sonia — British Female' },
  { value: 'en-GB-LibbyNeural',   label: 'Libby — British Female' },
  { value: 'en-US-GuyNeural',     label: 'Guy — American Male' },
  { value: 'en-US-JennyNeural',   label: 'Jenny — American Female' },
  { value: 'en-AU-NatashaNeural', label: 'Natasha — Australian Female' },
]

function getInitials(name = '') {
  return name.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase()
}

export default function CharacterModal({ projectId, character, onSave, onClose }) {
  const isEditing = !!character

  const [form, setForm] = useState({
    name: character?.name ?? '',
    role: character?.role ?? '',
    backstory: character?.backstory ?? '',
    visual_description: character?.visual_description ?? '',
    voice: character?.voice ?? 'en-GB-RyanNeural',
    voice_notes: character?.voice_notes ?? '',
  })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  // portraitOptions: list of relative paths returned from generate-portrait
  const [portraitOptions, setPortraitOptions] = useState([])
  // canonicalPath: the relative path stored in reference_image_path (no /static/series/ prefix)
  const [canonicalPath, setCanonicalPath] = useState(character?.reference_image_path ?? null)
  const [portraitError, setPortraitError] = useState('')
  const [selecting, setSelecting] = useState(null) // which path is being confirmed

  const handleChange = (e) => setForm((f) => ({ ...f, [e.target.name]: e.target.value }))

  const handleSubmit = async (e) => {
    e?.preventDefault()
    if (!form.name.trim()) { setError('Name is required.'); return }
    setError('')
    setSaving(true)
    try {
      const saved = isEditing
        ? await put(`/characters/${character.id}`, form)
        : await post(`/projects/${projectId}/characters`, form)
      onSave(saved)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save character.')
    } finally {
      setSaving(false)
    }
  }

  const handleGeneratePortrait = async () => {
    setGenerating(true)
    setPortraitError('')
    setPortraitOptions([])
    try {
      const data = await post(`/characters/${character.id}/generate-portrait`)
      // portrait_urls come back as "/static/series/{relative_path}"
      // Store relative paths by stripping the prefix so we can pass to select-portrait
      const relativePaths = (data.portrait_urls || []).map((url) =>
        url.replace(/^\/static\/series\//, '')
      )
      setPortraitOptions(relativePaths)
    } catch (err) {
      setPortraitError(err.response?.data?.detail || 'Portrait generation failed.')
    } finally {
      setGenerating(false)
    }
  }

  const handleSelectPortrait = async (relativePath) => {
    setSelecting(relativePath)
    try {
      const updated = await post(`/characters/${character.id}/select-portrait`, {
        portrait_path: relativePath,
      })
      setCanonicalPath(updated.reference_image_path)
    } catch (err) {
      setPortraitError(err.response?.data?.detail || 'Failed to set portrait.')
    } finally {
      setSelecting(null)
    }
  }

  // All portrait candidates to show — combine existing canonical + newly generated
  const allCandidates = portraitOptions.length > 0
    ? portraitOptions
    : canonicalPath
      ? [canonicalPath]
      : []

  return (
    <div className="modal-overlay">
      <div className="modal-pixel max-w-xl">

        {/* Header */}
        <div className="modal-header">
          <span className="heading-pixel-sm text-accent-400">
            {isEditing ? `✎ ${character.name}` : '+ NEW CHARACTER'}
          </span>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 font-pixel text-sm p-1">✕</button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {error && <div className="alert-error">✖ {error}</div>}

          {/* Portrait section */}
          {isEditing && (
            <div className="pixel-panel-sm p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="label-pixel">CHARACTER PORTRAIT</div>
                {canonicalPath && (
                  <span className="font-pixel text-px-green flex items-center gap-1" style={{ fontSize: '7px' }}>
                    <Star className="w-2.5 h-2.5 fill-current" /> CANONICAL SET
                  </span>
                )}
              </div>

              <div className="flex items-start gap-4">
                {/* Current canonical portrait preview */}
                <div className="w-20 h-20 bg-zinc-700 border-2 border-zinc-600 flex-shrink-0 flex items-center justify-center overflow-hidden"
                  style={{ boxShadow: '2px 2px 0 0 #000', imageRendering: 'pixelated' }}>
                  {canonicalPath ? (
                    <img src={`/static/series/${canonicalPath}`} alt={character.name} className="w-full h-full object-cover" />
                  ) : (
                    <span className="font-pixel text-accent-400" style={{ fontSize: '16px' }}>
                      {getInitials(character.name)}
                    </span>
                  )}
                </div>
                <div className="space-y-2">
                  <button onClick={handleGeneratePortrait} disabled={generating} className="btn-pixel-sm">
                    {generating ? <span className="pixel-spinner" /> : <Wand2 className="w-3 h-3" />}
                    {generating ? 'GENERATING...' : 'GEN PORTRAITS'}
                  </button>
                  <p className="text-retro text-zinc-600" style={{ fontSize: '14px' }}>
                    Generates 3 candidates — click one to make it canonical.
                    Canonical portrait feeds into video generation for visual consistency.
                  </p>
                  {portraitError && (
                    <p className="text-retro text-px-red" style={{ fontSize: '15px' }}>{portraitError}</p>
                  )}
                </div>
              </div>

              {/* Portrait candidates grid */}
              {allCandidates.length > 0 && (
                <div className="space-y-2">
                  <div className="font-pixel text-zinc-500" style={{ fontSize: '7px' }}>
                    {portraitOptions.length > 0 ? 'SELECT CANONICAL PORTRAIT:' : 'CURRENT PORTRAIT:'}
                  </div>
                  <div className="flex gap-3 flex-wrap">
                    {allCandidates.map((relPath, i) => {
                      const isCanonical = relPath === canonicalPath
                      const isSelecting = selecting === relPath
                      return (
                        <button
                          key={i}
                          onClick={() => handleSelectPortrait(relPath)}
                          disabled={isSelecting || isCanonical}
                          className={`relative w-24 h-24 border-2 overflow-hidden transition-all ${
                            isCanonical
                              ? 'border-px-green cursor-default'
                              : 'border-zinc-600 hover:border-accent-400'
                          }`}
                          style={{ boxShadow: '2px 2px 0 0 #000' }}
                          title={isCanonical ? 'Canonical portrait' : 'Set as canonical'}
                        >
                          <img
                            src={`/static/series/${relPath}`}
                            alt={`Portrait ${i + 1}`}
                            className="w-full h-full object-cover"
                          />
                          {isCanonical && (
                            <div className="absolute inset-0 bg-px-green/20 flex items-center justify-center">
                              <Star className="w-5 h-5 text-px-green drop-shadow-lg fill-current" />
                            </div>
                          )}
                          {isSelecting && (
                            <div className="absolute inset-0 bg-black/60 flex items-center justify-center">
                              <span className="pixel-spinner" />
                            </div>
                          )}
                          {!isCanonical && !isSelecting && (
                            <div className="absolute inset-0 bg-black/0 hover:bg-accent-500/20 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity">
                              <Check className="w-5 h-5 text-white drop-shadow-lg" />
                            </div>
                          )}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Form fields */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label-pixel">NAME *</label>
              <input name="name" value={form.name} onChange={handleChange} required className="input-pixel" placeholder="Character name" />
            </div>
            <div>
              <label className="label-pixel">ROLE</label>
              <input name="role" value={form.role} onChange={handleChange} className="input-pixel" placeholder="e.g. Protagonist" />
            </div>
          </div>

          <div>
            <label className="label-pixel">BACKSTORY</label>
            <textarea name="backstory" value={form.backstory} onChange={handleChange} rows={3}
              className="input-pixel resize-none" placeholder="Character history, motivations..." />
          </div>

          <div>
            <label className="label-pixel">VISUAL DESCRIPTION</label>
            <p className="text-retro text-zinc-500 mb-1" style={{ fontSize: '15px' }}>
              How this character looks — used in both portrait generation and video prompts
            </p>
            <textarea name="visual_description" value={form.visual_description} onChange={handleChange} rows={3}
              className="input-pixel resize-none" placeholder="Tall man in his 40s, weathered face, dark coat..." />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label-pixel">VOICE</label>
              <select name="voice" value={form.voice} onChange={handleChange} className="input-pixel">
                {VOICES.map((v) => (
                  <option key={v.value} value={v.value}>{v.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label-pixel">VOICE NOTES</label>
              <input name="voice_notes" value={form.voice_notes} onChange={handleChange}
                className="input-pixel" placeholder="Slow, weary, deliberate..." />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t-2 border-zinc-700">
          <button type="button" onClick={onClose} className="btn-pixel-ghost">CANCEL</button>
          <button onClick={handleSubmit} disabled={saving} className="btn-pixel">
            {saving ? '▶▶ SAVING...' : isEditing ? '▶ SAVE CHANGES' : '▶ CREATE CHARACTER'}
          </button>
        </div>
      </div>
    </div>
  )
}
