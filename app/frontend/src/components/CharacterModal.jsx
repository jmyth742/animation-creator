import React, { useState } from 'react'
import { X, Wand2, Check } from 'lucide-react'
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
  const [portraitOptions, setPortraitOptions] = useState([])
  const [selectedPortrait, setSelectedPortrait] = useState(character?.reference_image_path ?? null)
  const [portraitError, setPortraitError] = useState('')

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
      setPortraitOptions(data.portrait_urls || [])
    } catch (err) {
      setPortraitError(err.response?.data?.detail || 'Portrait generation failed.')
    } finally {
      setGenerating(false)
    }
  }

  const handleSelectPortrait = async (url) => {
    setSelectedPortrait(url)
    try {
      await put(`/characters/${character.id}`, { reference_image_path: url })
    } catch {}
  }

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
              <div className="label-pixel">CHARACTER PORTRAIT</div>
              <div className="flex items-start gap-4">
                <div className="w-20 h-20 bg-zinc-700 border-2 border-zinc-600 flex-shrink-0 flex items-center justify-center overflow-hidden"
                  style={{ boxShadow: '2px 2px 0 0 #000', imageRendering: 'pixelated' }}>
                  {character.portrait_url ? (
                    <img src={character.portrait_url} alt={character.name} className="w-full h-full object-cover" />
                  ) : (
                    <span className="font-pixel text-accent-400" style={{ fontSize: '16px' }}>
                      {getInitials(character.name)}
                    </span>
                  )}
                </div>
                <div>
                  <button onClick={handleGeneratePortrait} disabled={generating} className="btn-pixel-sm">
                    {generating ? <span className="pixel-spinner" /> : <Wand2 className="w-3 h-3" />}
                    {generating ? 'GENERATING...' : 'GEN PORTRAIT'}
                  </button>
                  {portraitError && <p className="text-retro text-px-red mt-2" style={{ fontSize: '15px' }}>{portraitError}</p>}
                </div>
              </div>
              {portraitOptions.length > 0 && (
                <div className="flex gap-3 flex-wrap pt-1">
                  {portraitOptions.map((url, i) => (
                    <button
                      key={i}
                      onClick={() => handleSelectPortrait(url)}
                      className={`relative w-20 h-20 border-2 overflow-hidden ${selectedPortrait === url ? 'border-accent-400' : 'border-zinc-600 hover:border-zinc-400'}`}
                      style={{ boxShadow: '2px 2px 0 0 #000' }}
                    >
                      <img src={url} alt={`Portrait ${i + 1}`} className="w-full h-full object-cover" />
                      {selectedPortrait === url && (
                        <div className="absolute inset-0 bg-accent-500/30 flex items-center justify-center">
                          <Check className="w-5 h-5 text-white drop-shadow-lg" />
                        </div>
                      )}
                    </button>
                  ))}
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
            <p className="text-retro text-zinc-500 mb-1" style={{ fontSize: '15px' }}>How this character looks for AI generation</p>
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
