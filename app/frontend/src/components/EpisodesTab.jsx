import React, { useEffect, useState } from 'react'
import {
  Plus, ChevronDown, ChevronRight, Clapperboard, Trash2,
  Pencil, Play, X, Check, MessageSquare, Eye, Film,
} from 'lucide-react'
import { get, post, put, del } from '../api/client'

// ── Scene editor modal ──────────────────────────────────────────────────────

function SceneModal({ episodeId, scene, locations, characters, onSave, onClose }) {
  const isNew = !scene

  const [form, setForm] = useState({
    visual: scene?.visual || '',
    narration: scene?.narration || '',
    clip_length: scene?.clip_length || 'medium',
    location_id: scene?.location_id || '',
    character_ids: scene?.characters?.map((c) => c.id) || [],
    dialogue: scene
      ? (() => {
          try { return JSON.parse(scene.dialogue) } catch { return [] }
        })()
      : [],
  })
  const [saving, setSaving] = useState(false)

  const setField = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const toggleCharacter = (id) => {
    setForm((f) => ({
      ...f,
      character_ids: f.character_ids.includes(id)
        ? f.character_ids.filter((c) => c !== id)
        : [...f.character_ids, id],
    }))
  }

  const addDialogueLine = () => {
    setForm((f) => ({ ...f, dialogue: [...f.dialogue, { character: '', line: '' }] }))
  }

  const updateDialogueLine = (idx, key, val) => {
    setForm((f) => {
      const d = [...f.dialogue]
      d[idx] = { ...d[idx], [key]: val }
      return { ...f, dialogue: d }
    })
  }

  const removeDialogueLine = (idx) => {
    setForm((f) => ({ ...f, dialogue: f.dialogue.filter((_, i) => i !== idx) }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload = {
        ...form,
        location_id: form.location_id ? Number(form.location_id) : null,
        dialogue: form.dialogue.filter((d) => d.character || d.line),
      }
      if (isNew) {
        await post(`/episodes/${episodeId}/scenes`, payload)
      } else {
        await put(`/scenes/${scene.id}`, payload)
      }
      onSave()
    } catch (err) {
      console.error(err)
      alert('Failed to save scene.')
    } finally {
      setSaving(false)
    }
  }

  const inputClass =
    'w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-accent-500 placeholder:text-zinc-600'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
          <h2 className="text-base font-bold text-zinc-100">{isNew ? 'New Scene' : 'Edit Scene'}</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-200 p-1 rounded">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Location + clip length */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Location</label>
              <select
                className={inputClass}
                value={form.location_id}
                onChange={setField('location_id')}
              >
                <option value="">— none —</option>
                {locations.map((loc) => (
                  <option key={loc.id} value={loc.id}>{loc.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Clip length</label>
              <select
                className={inputClass}
                value={form.clip_length}
                onChange={setField('clip_length')}
              >
                <option value="short">Short (~1 s)</option>
                <option value="medium">Medium (~1.5 s)</option>
                <option value="long">Long (~2 s)</option>
              </select>
            </div>
          </div>

          {/* Visual prompt */}
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">
              Visual prompt <span className="text-zinc-600">(sent to video generator)</span>
            </label>
            <textarea
              className={inputClass + ' resize-none'}
              rows={3}
              value={form.visual}
              onChange={setField('visual')}
              placeholder="Describe what the camera sees…"
            />
          </div>

          {/* Narration */}
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Narration</label>
            <textarea
              className={inputClass + ' resize-none'}
              rows={2}
              value={form.narration || ''}
              onChange={setField('narration')}
              placeholder="Optional narrator voiceover…"
            />
          </div>

          {/* Characters */}
          {characters.length > 0 && (
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-2">Characters in scene</label>
              <div className="flex flex-wrap gap-2">
                {characters.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => toggleCharacter(c.id)}
                    className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors border ${
                      form.character_ids.includes(c.id)
                        ? 'bg-accent-600 border-accent-500 text-white'
                        : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-500'
                    }`}
                  >
                    {c.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Dialogue */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-zinc-400">Dialogue</label>
              <button
                onClick={addDialogueLine}
                className="flex items-center gap-1 text-xs text-accent-400 hover:text-accent-300"
              >
                <Plus className="w-3 h-3" /> Add line
              </button>
            </div>
            {form.dialogue.length === 0 ? (
              <p className="text-xs text-zinc-600 italic">No dialogue — scene is visual/narration only.</p>
            ) : (
              <div className="space-y-2">
                {form.dialogue.map((d, idx) => (
                  <div key={idx} className="flex gap-2 items-start">
                    <input
                      className="w-32 shrink-0 bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1.5 text-xs text-zinc-100 focus:outline-none focus:border-accent-500"
                      value={d.character}
                      onChange={(e) => updateDialogueLine(idx, 'character', e.target.value)}
                      placeholder="Character"
                    />
                    <input
                      className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1.5 text-xs text-zinc-100 focus:outline-none focus:border-accent-500"
                      value={d.line}
                      onChange={(e) => updateDialogueLine(idx, 'line', e.target.value)}
                      placeholder="Line of dialogue…"
                    />
                    <button
                      onClick={() => removeDialogueLine(idx)}
                      className="text-zinc-600 hover:text-red-400 p-1.5 shrink-0"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-zinc-800">
          <button onClick={onClose} className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 rounded-lg hover:bg-zinc-800">
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !form.visual.trim()}
            className="flex items-center gap-2 px-5 py-2 text-sm bg-accent-600 hover:bg-accent-500 text-white rounded-lg disabled:opacity-50 font-medium"
          >
            {saving ? 'Saving…' : (isNew ? 'Add Scene' : 'Save Scene')}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Scene row ───────────────────────────────────────────────────────────────

function SceneRow({ scene, locations, characters, onEdit, onDelete }) {
  let dialogue = []
  try { dialogue = JSON.parse(scene.dialogue) } catch {}

  return (
    <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-4 group hover:border-zinc-700 transition-colors">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          {/* Meta row */}
          <div className="flex flex-wrap items-center gap-2 mb-2 text-xs text-zinc-500">
            {scene.location_name && (
              <span className="bg-zinc-800 px-2 py-0.5 rounded-md">{scene.location_name}</span>
            )}
            <span className="bg-zinc-800 px-2 py-0.5 rounded-md capitalize">{scene.clip_length}</span>
            {scene.characters?.length > 0 && (
              <span className="text-zinc-600">
                {scene.characters.map((c) => c.name).join(', ')}
              </span>
            )}
            <span
              className={`px-2 py-0.5 rounded-md ${
                scene.status === 'done' ? 'bg-green-900/40 text-green-400' :
                scene.status === 'generating' ? 'bg-accent-900/40 text-accent-400' :
                scene.status === 'error' ? 'bg-red-900/40 text-red-400' :
                'bg-zinc-800 text-zinc-500'
              }`}
            >
              {scene.status}
            </span>
          </div>

          {/* Visual */}
          {scene.visual && (
            <p className="text-sm text-zinc-300 line-clamp-2 mb-1">
              <Eye className="w-3 h-3 inline mr-1 text-zinc-600" />
              {scene.visual}
            </p>
          )}

          {/* Narration */}
          {scene.narration && (
            <p className="text-xs text-zinc-500 italic line-clamp-1">
              <MessageSquare className="w-3 h-3 inline mr-1" />
              {scene.narration}
            </p>
          )}

          {/* Dialogue preview */}
          {dialogue.length > 0 && (
            <div className="mt-2 space-y-0.5">
              {dialogue.slice(0, 2).map((d, i) => (
                <p key={i} className="text-xs text-zinc-500">
                  <span className="text-zinc-400 font-medium">{d.character}:</span> {d.line}
                </p>
              ))}
              {dialogue.length > 2 && (
                <p className="text-xs text-zinc-600">+{dialogue.length - 2} more lines</p>
              )}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          {scene.preview_url && (
            <a
              href={scene.preview_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-zinc-400 hover:text-accent-400 p-1.5 rounded-lg hover:bg-zinc-800"
            >
              <Film className="w-3.5 h-3.5" />
            </a>
          )}
          <button
            onClick={onEdit}
            className="text-zinc-400 hover:text-zinc-200 p-1.5 rounded-lg hover:bg-zinc-800"
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={onDelete}
            className="text-zinc-400 hover:text-red-400 p-1.5 rounded-lg hover:bg-zinc-800"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Episode row ─────────────────────────────────────────────────────────────

function EpisodeRow({ episode, project, onEpisodesChange, onProduce }) {
  const [expanded, setExpanded] = useState(false)
  const [scenes, setScenes] = useState(null) // null = not loaded
  const [loadingScenes, setLoadingScenes] = useState(false)
  const [sceneModal, setSceneModal] = useState(false) // false | null (new) | scene (edit)
  const [producing, setProducing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const locations = project.locations || []
  const characters = project.characters || []

  const loadScenes = async () => {
    if (scenes !== null) return
    setLoadingScenes(true)
    try {
      const data = await get(`/episodes/${episode.id}`)
      setScenes(data.scenes || [])
    } catch (err) {
      console.error(err)
      setScenes([])
    } finally {
      setLoadingScenes(false)
    }
  }

  const handleExpand = () => {
    setExpanded((v) => !v)
    if (!expanded) loadScenes()
  }

  const refreshScenes = async () => {
    try {
      const data = await get(`/episodes/${episode.id}`)
      setScenes(data.scenes || [])
    } catch (err) { console.error(err) }
  }

  const handleSceneSave = () => {
    setSceneModal(false)
    refreshScenes()
  }

  const handleSceneDelete = async (scene) => {
    if (!window.confirm(`Delete scene ${scene.order_idx + 1}?`)) return
    try {
      await del(`/scenes/${scene.id}`)
      refreshScenes()
    } catch (err) {
      console.error(err)
      alert('Failed to delete scene.')
    }
  }

  const handleDelete = async () => {
    if (!window.confirm(`Delete "${episode.title}"? All scenes will be lost.`)) return
    setDeleting(true)
    try {
      await del(`/episodes/${episode.id}`)
      onEpisodesChange()
    } catch (err) {
      console.error(err)
      alert('Failed to delete episode.')
      setDeleting(false)
    }
  }

  const handleProduce = async (quality) => {
    setProducing(true)
    try {
      const result = await post(`/episodes/${episode.id}/produce?quality=${quality}`)
      onProduce(result.job_id, {
        episodeTitle: episode.title,
        seriesSlug: project.series_slug,
        episodeNumber: episode.number,
      })
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to start production.'
      alert(detail)
    } finally {
      setProducing(false)
    }
  }

  return (
    <div className="bg-zinc-800/50 rounded-xl border border-zinc-800 overflow-hidden">
      {/* Episode header */}
      <div className="flex items-center gap-4 px-5 py-4 group">
        <button
          onClick={handleExpand}
          className="text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-zinc-500 uppercase tracking-wider">
              EP {String(episode.number).padStart(2, '0')}
            </span>
            <h3 className="text-sm font-semibold text-zinc-100 truncate">{episode.title}</h3>
          </div>
          {episode.summary && (
            <p className="text-xs text-zinc-500 mt-0.5 line-clamp-1">{episode.summary}</p>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="flex opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="text-zinc-500 hover:text-red-400 p-1.5 rounded-lg hover:bg-zinc-700 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="relative group/produce">
            <button
              onClick={() => handleProduce('draft')}
              disabled={producing}
              className="flex items-center gap-1.5 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 text-xs font-medium rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
            >
              <Play className="w-3 h-3" />
              {producing ? 'Starting…' : 'Produce'}
            </button>
            {/* Quality dropdown */}
            <div className="absolute right-0 top-full mt-1 bg-zinc-800 border border-zinc-700 rounded-xl shadow-xl z-10 hidden group-hover/produce:block min-w-32">
              <button
                onClick={() => handleProduce('draft')}
                className="w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700 rounded-t-xl"
              >
                Draft (fast)
              </button>
              <button
                onClick={() => handleProduce('quality')}
                className="w-full text-left px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700 rounded-b-xl"
              >
                Quality (slow)
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Scenes panel */}
      {expanded && (
        <div className="border-t border-zinc-800 px-5 pb-5 pt-4">
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
              Scenes {scenes ? `(${scenes.length})` : ''}
            </p>
            <button
              onClick={() => setSceneModal(null)}
              className="flex items-center gap-1 text-xs text-accent-400 hover:text-accent-300"
            >
              <Plus className="w-3 h-3" /> Add scene
            </button>
          </div>

          {loadingScenes ? (
            <div className="flex items-center justify-center py-8">
              <span className="w-5 h-5 border-2 border-zinc-700 border-t-accent-500 rounded-full animate-spin" />
            </div>
          ) : scenes && scenes.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-zinc-600 text-sm mb-3">No scenes yet</p>
              <button
                onClick={() => setSceneModal(null)}
                className="text-xs text-accent-400 hover:text-accent-300"
              >
                Add first scene
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {(scenes || []).map((scene, idx) => (
                <SceneRow
                  key={scene.id}
                  scene={{ ...scene, order_idx: idx }}
                  locations={locations}
                  characters={characters}
                  onEdit={() => setSceneModal(scene)}
                  onDelete={() => handleSceneDelete(scene)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Scene modal */}
      {sceneModal !== false && (
        <SceneModal
          episodeId={episode.id}
          scene={sceneModal}
          locations={locations}
          characters={characters}
          onSave={handleSceneSave}
          onClose={() => setSceneModal(false)}
        />
      )}
    </div>
  )
}

// ── Add Episode modal ───────────────────────────────────────────────────────

function AddEpisodeModal({ projectId, nextNumber, onSave, onClose }) {
  const [title, setTitle] = useState('')
  const [summary, setSummary] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    if (!title.trim()) return
    setSaving(true)
    try {
      await post(`/projects/${projectId}/episodes`, {
        number: nextNumber,
        title: title.trim(),
        summary: summary.trim(),
      })
      onSave()
    } catch (err) {
      console.error(err)
      alert('Failed to create episode.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-md shadow-2xl p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-bold text-zinc-100">New Episode</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-200 p-1 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Episode number</label>
            <input
              className="w-20 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-accent-500 text-center"
              type="number"
              min={1}
              defaultValue={nextNumber}
              disabled
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Title</label>
            <input
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-accent-500"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Episode title"
              autoFocus
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Summary</label>
            <textarea
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-accent-500 resize-none"
              rows={2}
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="Brief episode description…"
            />
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 rounded-lg hover:bg-zinc-800">
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!title.trim() || saving}
            className="px-5 py-2 text-sm bg-accent-600 hover:bg-accent-500 text-white rounded-lg disabled:opacity-50 font-medium"
          >
            {saving ? 'Creating…' : 'Create Episode'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main EpisodesTab ────────────────────────────────────────────────────────

export default function EpisodesTab({ projectId, project, episodes, onEpisodesChange, onProduce }) {
  const [showAddModal, setShowAddModal] = useState(false)
  const nextNumber = (episodes.length > 0 ? Math.max(...episodes.map((e) => e.number)) : 0) + 1

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-zinc-100">Episodes</h2>
          <p className="text-sm text-zinc-400 mt-0.5">
            {episodes.length} episode{episodes.length !== 1 ? 's' : ''}
            {episodes.length === 0 && ' — use Settings → Generate Scripts to create them with AI'}
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 bg-accent-600 hover:bg-accent-500 text-white font-medium rounded-xl px-4 py-2.5 text-sm transition-colors shadow-lg shadow-accent-900/30"
        >
          <Plus className="w-4 h-4" />
          New Episode
        </button>
      </div>

      {episodes.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <div className="w-16 h-16 bg-zinc-800 rounded-2xl flex items-center justify-center mb-4">
            <Clapperboard className="w-8 h-8 text-zinc-600" />
          </div>
          <h3 className="text-lg font-semibold text-zinc-300 mb-2">No episodes yet</h3>
          <p className="text-zinc-500 text-sm max-w-sm mb-5">
            Use <span className="text-zinc-300">Settings → Generate Scripts</span> to let Claude create a full series, or add episodes manually.
          </p>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 bg-accent-600 hover:bg-accent-500 text-white font-medium rounded-xl px-4 py-2 text-sm transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add episode manually
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {episodes
            .slice()
            .sort((a, b) => a.number - b.number)
            .map((ep) => (
              <EpisodeRow
                key={ep.id}
                episode={ep}
                project={project}
                onEpisodesChange={onEpisodesChange}
                onProduce={onProduce}
              />
            ))}
        </div>
      )}

      {showAddModal && (
        <AddEpisodeModal
          projectId={projectId}
          nextNumber={nextNumber}
          onSave={() => { setShowAddModal(false); onEpisodesChange() }}
          onClose={() => setShowAddModal(false)}
        />
      )}
    </div>
  )
}
