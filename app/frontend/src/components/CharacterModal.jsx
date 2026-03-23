import React, { useState, useEffect } from 'react'
import { X, Wand2, Check } from 'lucide-react'
import { post, put } from '../api/client'

const VOICES = [
  { value: 'en-GB-RyanNeural',    label: 'Ryan — British Male' },
  { value: 'en-GB-ThomasNeural', label: 'Thomas — British Male' },
  { value: 'en-GB-SoniaNeural',  label: 'Sonia — British Female' },
  { value: 'en-GB-LibbyNeural',  label: 'Libby — British Female' },
  { value: 'en-US-GuyNeural',    label: 'Guy — American Male' },
  { value: 'en-US-JennyNeural',  label: 'Jenny — American Female' },
  { value: 'en-AU-NatashaNeural',label: 'Natasha — Australian Female' },
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

  // Portrait generation state
  const [generating, setGenerating] = useState(false)
  const [portraitOptions, setPortraitOptions] = useState([])
  const [selectedPortrait, setSelectedPortrait] = useState(character?.reference_image_path ?? null)
  const [portraitError, setPortraitError] = useState('')

  const handleChange = (e) => {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) { setError('Name is required.'); return }
    setError('')
    setSaving(true)
    try {
      let saved
      if (isEditing) {
        saved = await put(`/characters/${character.id}`, form)
      } else {
        saved = await post(`/projects/${projectId}/characters`, form)
      }
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
    } catch (err) {
      console.error('Failed to update portrait:', err)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-xl bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
          <h2 className="text-base font-semibold text-zinc-100">
            {isEditing ? `Edit: ${character.name}` : 'New Character'}
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {error && (
            <div className="px-4 py-3 bg-red-950/60 border border-red-700/50 rounded-lg text-red-300 text-sm">
              {error}
            </div>
          )}

          {/* Portrait section (editing only) */}
          {isEditing && (
            <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-xl p-4 space-y-3">
              <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Portrait</h3>

              {/* Current portrait */}
              <div className="flex items-start gap-4">
                <div className="w-20 h-20 rounded-xl overflow-hidden bg-zinc-700 flex-shrink-0 flex items-center justify-center">
                  {character.portrait_url ? (
                    <img src={character.portrait_url} alt={character.name} className="w-full h-full object-cover" />
                  ) : (
                    <span className="text-2xl font-bold text-zinc-400">{getInitials(character.name)}</span>
                  )}
                </div>
                <div className="flex-1">
                  <button
                    onClick={handleGeneratePortrait}
                    disabled={generating}
                    className="flex items-center gap-2 px-4 py-2 bg-accent-700 hover:bg-accent-600 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
                  >
                    {generating ? (
                      <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    ) : (
                      <Wand2 className="w-3.5 h-3.5" />
                    )}
                    {generating ? 'Generating… (~30s)' : 'Generate Portrait'}
                  </button>
                  {generating && (
                    <p className="text-xs text-zinc-500 mt-2">
                      AI is creating portrait options. This may take ~30 seconds.
                    </p>
                  )}
                  {portraitError && (
                    <p className="text-xs text-red-400 mt-2">{portraitError}</p>
                  )}
                </div>
              </div>

              {/* Portrait options */}
              {portraitOptions.length > 0 && (
                <div>
                  <p className="text-xs text-zinc-400 mb-2">Select a portrait:</p>
                  <div className="flex gap-3 flex-wrap">
                    {portraitOptions.map((url, i) => (
                      <button
                        key={i}
                        onClick={() => handleSelectPortrait(url)}
                        className={`relative w-24 h-24 rounded-xl overflow-hidden border-2 transition-all ${
                          selectedPortrait === url
                            ? 'border-accent-500 ring-2 ring-accent-500/40'
                            : 'border-zinc-700 hover:border-zinc-500'
                        }`}
                      >
                        <img src={url} alt={`Portrait option ${i + 1}`} className="w-full h-full object-cover" />
                        {selectedPortrait === url && (
                          <div className="absolute inset-0 bg-accent-500/20 flex items-center justify-center">
                            <Check className="w-6 h-6 text-white drop-shadow-lg" />
                          </div>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Form fields */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wider">
                Name <span className="text-red-400">*</span>
              </label>
              <input
                name="name"
                value={form.name}
                onChange={handleChange}
                required
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2.5 text-zinc-100 placeholder-zinc-500 text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent transition"
                placeholder="Character name"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wider">
                Role
              </label>
              <input
                name="role"
                value={form.role}
                onChange={handleChange}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2.5 text-zinc-100 placeholder-zinc-500 text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent transition"
                placeholder="e.g. Protagonist"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wider">
              Backstory
            </label>
            <textarea
              name="backstory"
              value={form.backstory}
              onChange={handleChange}
              rows={3}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2.5 text-zinc-100 placeholder-zinc-500 text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent transition resize-none"
              placeholder="Character history, motivations, key events…"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wider">
              Visual Description
            </label>
            <p className="text-xs text-zinc-500 mb-1.5">Describe how this character looks for AI generation</p>
            <textarea
              name="visual_description"
              value={form.visual_description}
              onChange={handleChange}
              rows={4}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2.5 text-zinc-100 placeholder-zinc-500 text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent transition resize-none"
              placeholder="Tall man in his 40s, weathered face, dark coat, piercing grey eyes…"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wider">
                Voice
              </label>
              <select
                name="voice"
                value={form.voice}
                onChange={handleChange}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2.5 text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent transition"
              >
                {VOICES.map((v) => (
                  <option key={v.value} value={v.value}>
                    {v.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wider">
                Voice Notes
              </label>
              <input
                name="voice_notes"
                value={form.voice_notes}
                onChange={handleChange}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2.5 text-zinc-100 placeholder-zinc-500 text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent transition"
                placeholder="Slow, deliberate, weary…"
              />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-zinc-800">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="flex items-center gap-2 px-5 py-2 bg-accent-600 hover:bg-accent-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
          >
            {saving && (
              <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            )}
            {saving ? 'Saving…' : isEditing ? 'Save Changes' : 'Create Character'}
          </button>
        </div>
      </div>
    </div>
  )
}
