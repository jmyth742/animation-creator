import React, { useState } from 'react'
import { Camera, Star } from 'lucide-react'
import { post, put } from '../api/client'
import EnhanceButton from './EnhanceButton'

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

export default function CharacterModal({ projectId, character, projectContext = {}, onSave, onClose, onOpenPortraitStudio }) {
  const isEditing = !!character

  const [form, setForm] = useState({
    name: character?.name ?? '',
    role: character?.role ?? '',
    backstory: character?.backstory ?? '',
    visual_description: character?.visual_description ?? '',
    voice: character?.voice ?? 'en-GB-RyanNeural',
    voice_notes: character?.voice_notes ?? '',
    trigger_word: character?.trigger_word ?? '',
  })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

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
            <div className="pixel-panel-sm p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="label-pixel">CHARACTER PORTRAIT</div>
                {character.reference_image_path && (
                  <span className="font-pixel text-px-green flex items-center gap-1" style={{ fontSize: '7px' }}>
                    <Star className="w-2.5 h-2.5 fill-current" /> CANONICAL SET
                  </span>
                )}
              </div>
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 bg-zinc-700 border-2 border-zinc-600 flex-shrink-0 flex items-center justify-center overflow-hidden"
                  style={{ boxShadow: '2px 2px 0 0 #000' }}>
                  {character.reference_image_path ? (
                    <img src={`/static/series/${character.reference_image_path}`} alt={character.name} className="w-full h-full object-cover" />
                  ) : (
                    <span className="font-pixel text-accent-400" style={{ fontSize: '16px' }}>
                      {getInitials(character.name)}
                    </span>
                  )}
                </div>
                <div className="space-y-2">
                  <button
                    onClick={() => onOpenPortraitStudio?.(character)}
                    className="btn-pixel-sm flex items-center gap-1.5"
                  >
                    <Camera className="w-3 h-3" />
                    PORTRAIT STUDIO
                  </button>
                  <p className="text-retro text-zinc-600" style={{ fontSize: '14px' }}>
                    Generate & choose a portrait — it seeds visual consistency in video generation.
                  </p>
                </div>
              </div>
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
            <div className="flex items-center justify-between mb-0.5">
              <label className="label-pixel">BACKSTORY</label>
              <EnhanceButton
                fieldType="backstory"
                currentText={form.backstory}
                context={{ ...projectContext, character_name: form.name, character_role: form.role }}
                onSelect={(v) => setForm((f) => ({ ...f, backstory: v }))}
              />
            </div>
            <textarea name="backstory" value={form.backstory} onChange={handleChange} rows={3}
              className="input-pixel resize-none" placeholder="Character history, motivations..." />
          </div>

          <div>
            <div className="flex items-center justify-between mb-0.5">
              <label className="label-pixel">VISUAL DESCRIPTION</label>
              <EnhanceButton
                fieldType="character_visual"
                currentText={form.visual_description}
                context={{ ...projectContext, character_name: form.name, character_role: form.role }}
                onSelect={(v) => setForm((f) => ({ ...f, visual_description: v }))}
              />
            </div>
            <p className="text-retro text-zinc-500 mb-1" style={{ fontSize: '15px' }}>
              How this character looks — used in both portrait generation and video prompts
            </p>
            <textarea name="visual_description" value={form.visual_description} onChange={handleChange} rows={3}
              className="input-pixel resize-none" placeholder="Tall man in his 40s, weathered face, dark coat..." />
          </div>

          {/* LoRA trigger word */}
          {isEditing && character?.lora_path && (
            <div>
              <label className="label-pixel">LORA TRIGGER WORD</label>
              <p className="text-retro text-zinc-500 mb-1" style={{ fontSize: '15px' }}>
                This word activates the LoRA — it gets injected into video prompts automatically
              </p>
              <input name="trigger_word" value={form.trigger_word} onChange={handleChange}
                className="input-pixel" placeholder="e.g. bibi, Reemi, sksstyle" />
            </div>
          )}

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
