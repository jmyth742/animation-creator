import React, { useState } from 'react'
import { MapPin, Users, Film, X, ChevronRight, Clock } from 'lucide-react'
import { post, put } from '../api/client'
import EnhanceButton from './EnhanceButton'

const CLIP_LABELS = { short: 'SHORT ~2s', medium: 'MED ~2.7s', long: 'LONG ~3.4s' }

export default function SceneComposerModal({ episodeId, scene, locations, characters, projectContext = {}, onSave, onClose }) {
  const isNew = !scene
  const [form, setForm] = useState({
    visual: scene?.visual || '',
    narration: scene?.narration || '',
    clip_length: scene?.clip_length || 'medium',
    location_id: scene?.location_id ?? null,
    character_ids: scene?.characters?.map((c) => c.id) || [],
    dialogue: scene ? (() => { try { return JSON.parse(scene.dialogue) } catch { return [] } })() : [],
  })
  const [saving, setSaving] = useState(false)

  const selectedLoc = locations.find((l) => l.id === Number(form.location_id)) ?? null
  const selectedChars = characters.filter((c) => form.character_ids.includes(c.id))

  const selectLoc = (id) => setForm((f) => ({ ...f, location_id: id }))
  const toggleChar = (id) => setForm((f) => ({
    ...f,
    character_ids: f.character_ids.includes(id)
      ? f.character_ids.filter((c) => c !== id)
      : [...f.character_ids, id],
  }))

  const addLine = () => setForm((f) => ({ ...f, dialogue: [...f.dialogue, { character: '', line: '' }] }))
  const updateLine = (idx, key, val) => setForm((f) => {
    const d = [...f.dialogue]; d[idx] = { ...d[idx], [key]: val }; return { ...f, dialogue: d }
  })
  const removeLine = (idx) => setForm((f) => ({ ...f, dialogue: f.dialogue.filter((_, i) => i !== idx) }))

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload = {
        ...form,
        location_id: form.location_id ? Number(form.location_id) : null,
        dialogue: form.dialogue.filter((d) => d.character || d.line),
      }
      isNew
        ? await post(`/episodes/${episodeId}/scenes`, payload)
        : await put(`/scenes/${scene.id}`, payload)
      onSave()
    } catch {
      alert('Failed to save scene.')
    } finally {
      setSaving(false)
    }
  }

  const sceneLabel = isNew ? 'NEW SCENE' : `SCENE ${(scene.order_idx ?? 0) + 1}`

  return (
    <div className="modal-overlay">
      <div className="modal-pixel w-full" style={{ maxWidth: '960px' }}>

        {/* Header */}
        <div className="modal-header">
          <div className="flex items-center gap-3">
            <span className="text-lg">🎬</span>
            <div>
              <span className="heading-pixel-sm text-accent-400">SCENE COMPOSER</span>
              <span className="font-pixel text-zinc-500 ml-2" style={{ fontSize: '7px' }}>— {sceneLabel}</span>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 font-pixel text-sm p-1">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto">

          {/* ── TOP ROW: Stage preview + clip length ──────────────────────────── */}
          <div className="bg-zinc-900 border-b-2 border-zinc-700 px-6 py-4">
            <div className="flex items-start gap-6">

              {/* Assembled stage */}
              <div className="flex items-center gap-3 flex-1 min-w-0">

                {/* Location backdrop */}
                <div className="flex-shrink-0 flex flex-col items-center gap-1">
                  <div className="font-pixel text-zinc-600" style={{ fontSize: '6px' }}>BACKDROP</div>
                  <div
                    className={`border-2 overflow-hidden flex items-center justify-center flex-shrink-0 ${
                      selectedLoc ? 'border-accent-500' : 'border-dashed border-zinc-700'
                    }`}
                    style={{ width: '160px', height: '90px', background: '#0d1117' }}
                  >
                    {selectedLoc?.reference_url ? (
                      <img src={selectedLoc.reference_url} alt={selectedLoc.name} className="w-full h-full object-cover" />
                    ) : selectedLoc ? (
                      <div className="text-center px-2">
                        <MapPin className="w-4 h-4 text-accent-500 mx-auto mb-1" />
                        <span className="font-pixel text-zinc-400" style={{ fontSize: '6px' }}>{selectedLoc.name}</span>
                      </div>
                    ) : (
                      <div className="text-center">
                        <Film className="w-5 h-5 text-zinc-700 mx-auto mb-1" />
                        <span className="font-pixel text-zinc-700" style={{ fontSize: '6px' }}>SELECT LOCATION</span>
                      </div>
                    )}
                  </div>
                  {selectedLoc && (
                    <span className="font-pixel text-accent-400" style={{ fontSize: '6px' }}>📍 {selectedLoc.name}</span>
                  )}
                </div>

                <ChevronRight className="w-4 h-4 text-zinc-700 flex-shrink-0" />

                {/* Cast on stage */}
                <div className="flex-1">
                  <div className="font-pixel text-zinc-600 mb-2" style={{ fontSize: '6px' }}>
                    CAST IN SCENE {selectedChars.length > 0 ? `(${selectedChars.length})` : ''}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {selectedChars.map((c) => (
                      <div key={c.id} className="relative flex flex-col items-center gap-1">
                        <div
                          className="border-2 border-px-green overflow-hidden flex items-center justify-center"
                          style={{ width: '52px', height: '68px', background: '#0d1117' }}
                        >
                          {c.portrait_url ? (
                            <img src={c.portrait_url} alt={c.name} className="w-full h-full object-cover" />
                          ) : (
                            <span className="font-pixel text-px-green" style={{ fontSize: '12px' }}>
                              {c.name.slice(0, 2).toUpperCase()}
                            </span>
                          )}
                        </div>
                        <span className="font-pixel text-px-green text-center" style={{ fontSize: '5px', maxWidth: '52px', lineHeight: 1.3 }}>
                          {c.name}
                        </span>
                        <button
                          onClick={() => toggleChar(c.id)}
                          className="absolute -top-1 -right-1 bg-zinc-800 border border-zinc-600 text-zinc-500 hover:text-px-red hover:border-px-red w-3.5 h-3.5 flex items-center justify-center"
                          title="Remove from scene"
                        >
                          <X className="w-2 h-2" />
                        </button>
                      </div>
                    ))}
                    {selectedChars.length === 0 && (
                      <div
                        className="border-2 border-dashed border-zinc-700 flex items-center justify-center"
                        style={{ width: '52px', height: '68px' }}
                      >
                        <Users className="w-4 h-4 text-zinc-700" />
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Clip length selector */}
              <div className="flex-shrink-0 flex flex-col gap-1">
                <div className="font-pixel text-zinc-600 mb-1" style={{ fontSize: '6px' }}>
                  <Clock className="w-2.5 h-2.5 inline mr-0.5" />CLIP LENGTH
                </div>
                {Object.entries(CLIP_LABELS).map(([len, label]) => (
                  <button
                    key={len}
                    onClick={() => setForm((f) => ({ ...f, clip_length: len }))}
                    className={`font-pixel border-2 px-3 py-1.5 text-left transition-colors ${
                      form.clip_length === len
                        ? 'border-accent-400 text-accent-300 bg-accent-950'
                        : 'border-zinc-700 text-zinc-500 hover:border-zinc-500 hover:text-zinc-300'
                    }`}
                    style={{ fontSize: '6px', boxShadow: form.clip_length === len ? '2px 2px 0 0 #000' : 'none' }}
                  >
                    {form.clip_length === len ? '▶ ' : '  '}{label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="p-6 space-y-6">

            {/* ── LOCATION PICKER ──────────────────────────────────────────────── */}
            <div>
              <div className="label-pixel mb-3 flex items-center gap-2">
                <MapPin className="w-3 h-3" /> CHOOSE BACKDROP
              </div>
              <div className="flex flex-wrap gap-2">
                {/* None */}
                <button
                  onClick={() => selectLoc(null)}
                  className={`border-2 flex flex-col items-center justify-center gap-1 transition-all flex-shrink-0 ${
                    !form.location_id ? 'border-accent-400 bg-accent-950' : 'border-zinc-700 hover:border-zinc-500'
                  }`}
                  style={{ width: '88px', height: '58px' }}
                >
                  <Film className="w-4 h-4 text-zinc-600" />
                  <span className="font-pixel text-zinc-600" style={{ fontSize: '6px' }}>NONE</span>
                </button>

                {locations.length === 0 && (
                  <p className="text-retro text-zinc-600 self-center italic ml-2" style={{ fontSize: '15px' }}>
                    No locations yet — add them in the Locations tab.
                  </p>
                )}

                {locations.map((loc) => {
                  const isSelected = Number(form.location_id) === loc.id
                  return (
                    <button
                      key={loc.id}
                      onClick={() => selectLoc(loc.id)}
                      className={`relative border-2 overflow-hidden flex-shrink-0 transition-all ${
                        isSelected
                          ? 'border-accent-400'
                          : 'border-zinc-700 hover:border-zinc-400'
                      }`}
                      style={{
                        width: '88px', height: '58px', background: '#0d1117',
                        boxShadow: isSelected ? '2px 2px 0 0 #000' : 'none',
                        transform: isSelected ? 'scale(1.05)' : 'scale(1)',
                      }}
                    >
                      {loc.reference_url ? (
                        <img src={loc.reference_url} alt={loc.name} className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <MapPin className="w-4 h-4 text-zinc-600" />
                        </div>
                      )}
                      <div className="absolute inset-x-0 bottom-0 bg-black/75 px-1 py-0.5">
                        <span className="font-pixel text-zinc-200 block truncate" style={{ fontSize: '5px' }}>{loc.name}</span>
                      </div>
                      {isSelected && (
                        <div className="absolute top-1 right-1 w-2.5 h-2.5 bg-accent-400 border border-accent-300" />
                      )}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* ── CHARACTER PICKER ─────────────────────────────────────────────── */}
            <div>
              <div className="label-pixel mb-3 flex items-center gap-2">
                <Users className="w-3 h-3" /> CHOOSE CAST
                <span className="text-zinc-600 font-pixel normal-case" style={{ fontSize: '7px' }}>
                  (click to add/remove from scene)
                </span>
              </div>

              {characters.length === 0 ? (
                <p className="text-retro text-zinc-600 italic" style={{ fontSize: '15px' }}>
                  No characters yet — add them in the Characters tab.
                </p>
              ) : (
                <div className="flex flex-wrap gap-3">
                  {characters.map((c) => {
                    const isSelected = form.character_ids.includes(c.id)
                    return (
                      <button
                        key={c.id}
                        onClick={() => toggleChar(c.id)}
                        className="relative flex flex-col items-center gap-1 group/char"
                      >
                        <div
                          className={`border-2 overflow-hidden transition-all ${
                            isSelected
                              ? 'border-px-green'
                              : 'border-zinc-700 hover:border-zinc-400 opacity-60 hover:opacity-100'
                          }`}
                          style={{ width: '60px', height: '80px', background: '#0d1117' }}
                        >
                          {c.portrait_url ? (
                            <img src={c.portrait_url} alt={c.name} className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full flex flex-col items-center justify-center gap-1">
                              <span
                                className={`font-pixel ${isSelected ? 'text-px-green' : 'text-zinc-600'}`}
                                style={{ fontSize: '14px' }}
                              >
                                {c.name.slice(0, 2).toUpperCase()}
                              </span>
                            </div>
                          )}
                          {isSelected && (
                            <div className="absolute top-1 left-1 bg-px-green w-3 h-3 flex items-center justify-center">
                              <span className="text-black font-bold" style={{ fontSize: '8px', lineHeight: 1 }}>✓</span>
                            </div>
                          )}
                        </div>
                        <span
                          className={`font-pixel truncate text-center transition-colors ${
                            isSelected ? 'text-px-green' : 'text-zinc-600 group-hover/char:text-zinc-400'
                          }`}
                          style={{ fontSize: '6px', maxWidth: '60px' }}
                        >
                          {c.name}
                        </span>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

            {/* ── VISUAL + NARRATION ───────────────────────────────────────────── */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="label-pixel">
                    WHAT HAPPENS <span className="text-zinc-600 normal-case font-pixel" style={{ fontSize: '7px' }}>(sent to video AI)</span>
                  </label>
                  <EnhanceButton
                    fieldType="scene_visual"
                    currentText={form.visual}
                    context={{
                      ...projectContext,
                      location: selectedLoc?.name,
                      characters: selectedChars.map((c) => c.name).join(', '),
                    }}
                    onSelect={(v) => setForm((f) => ({ ...f, visual: v }))}
                  />
                </div>
                <textarea
                  className="input-pixel resize-none"
                  rows={4}
                  value={form.visual}
                  onChange={(e) => setForm((f) => ({ ...f, visual: e.target.value }))}
                  placeholder="Describe what the camera sees — action, framing, mood..."
                  autoFocus={isNew}
                />
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="label-pixel">
                    NARRATION <span className="text-zinc-600 normal-case font-pixel" style={{ fontSize: '7px' }}>(optional voiceover)</span>
                  </label>
                  <EnhanceButton
                    fieldType="narration"
                    currentText={form.narration || ''}
                    context={{
                      ...projectContext,
                      location: selectedLoc?.name,
                      scene_visual: form.visual,
                    }}
                    onSelect={(v) => setForm((f) => ({ ...f, narration: v }))}
                  />
                </div>
                <textarea
                  className="input-pixel resize-none"
                  rows={4}
                  value={form.narration || ''}
                  onChange={(e) => setForm((f) => ({ ...f, narration: e.target.value }))}
                  placeholder="Narrator speaks while the clip plays..."
                />
              </div>
            </div>

            {/* ── DIALOGUE ─────────────────────────────────────────────────────── */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="label-pixel">DIALOGUE</label>
                <button
                  onClick={addLine}
                  className="font-pixel text-accent-400 hover:text-accent-300 flex items-center gap-1"
                  style={{ fontSize: '7px' }}
                >
                  + ADD LINE
                </button>
              </div>

              {form.dialogue.length === 0 ? (
                <div className="border border-dashed border-zinc-700 px-4 py-3 text-center">
                  <p className="text-retro text-zinc-600 italic" style={{ fontSize: '15px' }}>
                    No dialogue — purely visual or narration only.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {form.dialogue.map((d, idx) => (
                    <div key={idx} className="flex gap-2 items-start">
                      <select
                        className="input-pixel w-36 shrink-0"
                        value={d.character}
                        onChange={(e) => updateLine(idx, 'character', e.target.value)}
                      >
                        <option value="">— speaker —</option>
                        {characters.map((c) => (
                          <option key={c.id} value={c.name}>{c.name}</option>
                        ))}
                      </select>
                      <input
                        className="input-pixel flex-1"
                        value={d.line}
                        onChange={(e) => updateLine(idx, 'line', e.target.value)}
                        placeholder="Spoken line..."
                      />
                      <button
                        onClick={() => removeLine(idx)}
                        className="text-zinc-600 hover:text-px-red p-2 shrink-0 border border-zinc-700 hover:border-px-red"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t-2 border-zinc-700">
          <div className="text-retro text-zinc-500" style={{ fontSize: '14px' }}>
            {[
              selectedLoc && `📍 ${selectedLoc.name}`,
              selectedChars.length > 0 && `👥 ${selectedChars.map((c) => c.name).join(', ')}`,
            ].filter(Boolean).join('  ·  ') || 'No location or cast selected yet'}
          </div>
          <div className="flex gap-3">
            <button onClick={onClose} className="btn-pixel-ghost">CANCEL</button>
            <button
              onClick={handleSave}
              disabled={saving || !form.visual.trim()}
              className="btn-pixel disabled:opacity-50"
            >
              {saving ? 'SAVING...' : isNew ? '+ ADD SCENE' : '▶ SAVE SCENE'}
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
