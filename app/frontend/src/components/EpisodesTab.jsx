import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Plus, ChevronDown, ChevronRight, Trash2, Pencil, Play, X, Eye, Film, RefreshCw } from 'lucide-react'
import { get, post, put, del } from '../api/client'

// ── Scene modal ─────────────────────────────────────────────────────────────

function SceneModal({ episodeId, scene, locations, characters, onSave, onClose }) {
  const isNew = !scene
  const [form, setForm] = useState({
    visual: scene?.visual || '',
    narration: scene?.narration || '',
    clip_length: scene?.clip_length || 'medium',
    location_id: scene?.location_id || '',
    character_ids: scene?.characters?.map((c) => c.id) || [],
    dialogue: scene ? (() => { try { return JSON.parse(scene.dialogue) } catch { return [] } })() : [],
  })
  const [saving, setSaving] = useState(false)

  const setField = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const toggleChar = (id) => setForm((f) => ({
    ...f,
    character_ids: f.character_ids.includes(id) ? f.character_ids.filter((c) => c !== id) : [...f.character_ids, id]
  }))
  const addLine = () => setForm((f) => ({ ...f, dialogue: [...f.dialogue, { character: '', line: '' }] }))
  const updateLine = (idx, key, val) => setForm((f) => {
    const d = [...f.dialogue]; d[idx] = { ...d[idx], [key]: val }; return { ...f, dialogue: d }
  })
  const removeLine = (idx) => setForm((f) => ({ ...f, dialogue: f.dialogue.filter((_, i) => i !== idx) }))

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload = { ...form, location_id: form.location_id ? Number(form.location_id) : null,
        dialogue: form.dialogue.filter((d) => d.character || d.line) }
      isNew ? await post(`/episodes/${episodeId}/scenes`, payload) : await put(`/scenes/${scene.id}`, payload)
      onSave()
    } catch { alert('Failed to save scene.') }
    finally { setSaving(false) }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-pixel max-w-2xl">
        <div className="modal-header">
          <span className="heading-pixel-sm text-accent-400">{isNew ? '+ NEW SCENE' : '✎ EDIT SCENE'}</span>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 font-pixel text-sm p-1">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label-pixel">LOCATION</label>
              <select className="input-pixel" value={form.location_id} onChange={setField('location_id')}>
                <option value="">— none —</option>
                {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label-pixel">CLIP LENGTH</label>
              <select className="input-pixel" value={form.clip_length} onChange={setField('clip_length')}>
                <option value="short">SHORT (~1s)</option>
                <option value="medium">MEDIUM (~1.5s)</option>
                <option value="long">LONG (~2s)</option>
              </select>
            </div>
          </div>

          <div>
            <label className="label-pixel">VISUAL PROMPT <span className="text-zinc-600">(sent to video AI)</span></label>
            <textarea className="input-pixel resize-none" rows={3} value={form.visual} onChange={setField('visual')}
              placeholder="Describe what the camera sees..." />
          </div>

          <div>
            <label className="label-pixel">NARRATION</label>
            <textarea className="input-pixel resize-none" rows={2} value={form.narration || ''} onChange={setField('narration')}
              placeholder="Optional narrator voiceover..." />
          </div>

          {characters.length > 0 && (
            <div>
              <label className="label-pixel mb-2">CHARACTERS IN SCENE</label>
              <div className="flex flex-wrap gap-2">
                {characters.map((c) => (
                  <button key={c.id} onClick={() => toggleChar(c.id)}
                    className={`font-pixel border-2 px-3 py-1 transition-colors ${form.character_ids.includes(c.id) ? 'bg-accent-700 border-accent-400 text-white' : 'bg-zinc-800 border-zinc-600 text-zinc-400 hover:border-zinc-400'}`}
                    style={{ fontSize: '7px', boxShadow: '2px 2px 0 0 #000' }}>
                    {c.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="label-pixel">DIALOGUE</label>
              <button onClick={addLine} className="font-pixel text-accent-400 hover:text-accent-300" style={{ fontSize: '7px' }}>
                + ADD LINE
              </button>
            </div>
            {form.dialogue.length === 0
              ? <p className="text-retro text-zinc-600 italic" style={{ fontSize: '15px' }}>No dialogue — visual/narration only.</p>
              : <div className="space-y-2">
                {form.dialogue.map((d, idx) => (
                  <div key={idx} className="flex gap-2 items-start">
                    <input className="input-pixel w-32 shrink-0" value={d.character}
                      onChange={(e) => updateLine(idx, 'character', e.target.value)} placeholder="Character" />
                    <input className="input-pixel flex-1" value={d.line}
                      onChange={(e) => updateLine(idx, 'line', e.target.value)} placeholder="Line..." />
                    <button onClick={() => removeLine(idx)} className="text-zinc-600 hover:text-px-red p-2 shrink-0 border border-zinc-700">
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            }
          </div>
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t-2 border-zinc-700">
          <button onClick={onClose} className="btn-pixel-ghost">CANCEL</button>
          <button onClick={handleSave} disabled={saving || !form.visual.trim()} className="btn-pixel">
            {saving ? 'SAVING...' : isNew ? '+ ADD SCENE' : '▶ SAVE SCENE'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Scene preview modal ───────────────────────────────────────────────────────

function ScenePreviewModal({ url, onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-pixel max-w-lg" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span className="heading-pixel-sm text-accent-400">▶ SCENE PREVIEW</span>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 font-pixel text-sm p-1">✕</button>
        </div>
        <div className="p-4">
          <video
            src={url}
            controls
            autoPlay
            loop
            className="w-full border-2 border-zinc-700"
            style={{ background: '#000', imageRendering: 'pixelated' }}
          />
        </div>
      </div>
    </div>
  )
}

// ── Scene row ────────────────────────────────────────────────────────────────

function SceneRow({ scene, onEdit, onDelete, onRegenerate }) {
  const [previewOpen, setPreviewOpen] = useState(false)
  let dialogue = []
  try { dialogue = JSON.parse(scene.dialogue) } catch {}

  const isGenerating = scene.status === 'generating'
  const statusColor = scene.status === 'done' ? 'text-px-green' : scene.status === 'error' ? 'text-px-red'
    : isGenerating ? 'text-accent-400' : 'text-zinc-500'

  return (
    <>
      <div className="bg-zinc-900 border-2 border-zinc-700 p-3 group hover:border-zinc-600 transition-colors"
        style={{ boxShadow: '2px 2px 0 0 #000' }}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap gap-2 mb-1.5">
              {scene.location_name && <span className="badge-pixel">📍 {scene.location_name}</span>}
              <span className="badge-pixel">{scene.clip_length?.toUpperCase()}</span>
              <span className={`font-pixel flex items-center gap-1 ${statusColor}`} style={{ fontSize: '7px' }}>
                {isGenerating && <span className="pixel-spinner" style={{ width: '8px', height: '8px' }} />}
                {scene.status?.toUpperCase()}
              </span>
            </div>
            {scene.visual && (
              <p className="text-retro text-zinc-300 line-clamp-2 mb-1" style={{ fontSize: '16px' }}>
                <Eye className="w-3 h-3 inline mr-1 text-zinc-600" />{scene.visual}
              </p>
            )}
            {dialogue.length > 0 && (
              <div className="mt-1 space-y-0.5">
                {dialogue.slice(0, 2).map((d, i) => (
                  <p key={i} className="text-retro text-zinc-500" style={{ fontSize: '14px' }}>
                    <span className="text-zinc-400">{d.character}:</span> {d.line}
                  </p>
                ))}
              </div>
            )}

            {/* Inline clip preview strip */}
            {scene.preview_url && (
              <div className="mt-2">
                <video
                  src={scene.preview_url}
                  autoPlay
                  loop
                  muted
                  playsInline
                  className="h-16 border border-zinc-700 cursor-pointer hover:border-accent-500 transition-colors"
                  style={{ aspectRatio: '16/9', objectFit: 'cover' }}
                  onClick={() => setPreviewOpen(true)}
                  title="Click to expand"
                />
              </div>
            )}
          </div>

          <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
            {scene.preview_url && (
              <button onClick={() => setPreviewOpen(true)}
                className="p-1.5 border border-zinc-600 text-zinc-400 hover:text-accent-400 hover:border-accent-600"
                title="Preview clip">
                <Film className="w-3 h-3" />
              </button>
            )}
            <div className="relative group/regen">
              <button
                onClick={() => onRegenerate(scene, 'draft')}
                disabled={isGenerating}
                className="p-1.5 border border-zinc-600 text-zinc-400 hover:text-px-green hover:border-px-green disabled:opacity-40 disabled:cursor-not-allowed"
                title="Regenerate clip">
                <RefreshCw className={`w-3 h-3 ${isGenerating ? 'animate-spin' : ''}`} />
              </button>
              {/* Quality dropdown */}
              <div className="absolute right-0 top-full mt-1 bg-zinc-800 border-2 border-zinc-600 z-20 hidden group-hover/regen:block min-w-36"
                style={{ boxShadow: '3px 3px 0 0 #000' }}>
                <button onClick={() => onRegenerate(scene, 'draft')}
                  className="w-full text-left px-3 py-2 text-retro text-zinc-300 hover:bg-zinc-700 border-b border-zinc-700" style={{ fontSize: '16px' }}>
                  ⟳ DRAFT (FAST)
                </button>
                <button onClick={() => onRegenerate(scene, 'quality')}
                  className="w-full text-left px-3 py-2 text-retro text-zinc-300 hover:bg-zinc-700" style={{ fontSize: '16px' }}>
                  ★ QUALITY (SLOW)
                </button>
              </div>
            </div>
            <button onClick={onEdit} className="p-1.5 border border-zinc-600 text-zinc-400 hover:text-accent-400 hover:border-accent-600">
              <Pencil className="w-3 h-3" />
            </button>
            <button onClick={onDelete} className="p-1.5 border border-zinc-600 text-zinc-400 hover:text-px-red hover:border-px-red">
              <Trash2 className="w-3 h-3" />
            </button>
          </div>
        </div>
      </div>

      {previewOpen && scene.preview_url && (
        <ScenePreviewModal url={scene.preview_url} onClose={() => setPreviewOpen(false)} />
      )}
    </>
  )
}

// ── Episode row ──────────────────────────────────────────────────────────────

function EpisodeRow({ episode, project, onEpisodesChange, onProduce }) {
  const [expanded, setExpanded] = useState(false)
  const [scenes, setScenes] = useState(null)
  const [loadingScenes, setLoadingScenes] = useState(false)
  const [sceneModal, setSceneModal] = useState(false)
  const [producing, setProducing] = useState(false)
  const pollRef = useRef(null)

  const locations = project.locations || []
  const characters = project.characters || []

  const loadScenes = async () => {
    if (scenes !== null) return
    setLoadingScenes(true)
    try { const data = await get(`/episodes/${episode.id}`); setScenes(data.scenes || []) }
    catch { setScenes([]) }
    finally { setLoadingScenes(false) }
  }

  const refreshScenes = useCallback(async () => {
    try { const data = await get(`/episodes/${episode.id}`); setScenes(data.scenes || []) }
    catch {}
  }, [episode.id])

  const handleExpand = () => { setExpanded((v) => !v); if (!expanded) loadScenes() }

  // Poll every 3s while any scene is generating
  useEffect(() => {
    if (!scenes) return
    const anyGenerating = scenes.some((s) => s.status === 'generating')
    if (anyGenerating && !pollRef.current) {
      pollRef.current = setInterval(refreshScenes, 3000)
    } else if (!anyGenerating && pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    }
  }, [scenes, refreshScenes])

  const handleSceneDelete = async (scene) => {
    if (!window.confirm(`DELETE scene ${scene.order_idx + 1}?`)) return
    try { await del(`/scenes/${scene.id}`); refreshScenes() }
    catch { alert('Failed to delete scene.') }
  }

  const handleRegenerate = async (scene, quality) => {
    try {
      await post(`/scenes/${scene.id}/regenerate?quality=${quality}`)
      // Optimistically mark as generating so the spinner appears immediately
      setScenes((prev) => prev.map((s) => s.id === scene.id ? { ...s, status: 'generating' } : s))
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to start regeneration.')
    }
  }

  const handleDelete = async () => {
    if (!window.confirm(`DELETE "${episode.title}"? All scenes will be lost.`)) return
    try { await del(`/episodes/${episode.id}`); onEpisodesChange() }
    catch { alert('Failed to delete episode.') }
  }

  const handleProduce = async (quality) => {
    setProducing(true)
    try {
      const result = await post(`/episodes/${episode.id}/produce?quality=${quality}`)
      onProduce(result.job_id, { episodeTitle: episode.title, seriesSlug: project.series_slug, episodeNumber: episode.number })
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to start production.')
    } finally { setProducing(false) }
  }

  return (
    <div className="bg-zinc-800 border-2 border-zinc-700 overflow-hidden" style={{ boxShadow: '3px 3px 0 0 #000' }}>
      <div className="flex items-center gap-3 px-4 py-3 group">
        <button onClick={handleExpand} className="text-zinc-500 hover:text-accent-400 transition-colors">
          {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="font-pixel text-accent-500" style={{ fontSize: '7px' }}>
              EP {String(episode.number).padStart(2, '0')}
            </span>
            <span className="font-pixel text-zinc-100 truncate" style={{ fontSize: '8px' }}>{episode.title}</span>
          </div>
          {episode.summary && (
            <p className="text-retro text-zinc-500 line-clamp-1" style={{ fontSize: '15px' }}>{episode.summary}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={handleDelete}
            className="text-zinc-600 hover:text-px-red p-1 opacity-0 group-hover:opacity-100 transition-opacity border border-transparent hover:border-px-red">
            <Trash2 className="w-3 h-3" />
          </button>
          <div className="relative group/produce">
            <button onClick={() => handleProduce('draft')} disabled={producing} className="btn-pixel-sm">
              <Play className="w-2.5 h-2.5" />{producing ? 'STARTING...' : 'PRODUCE'}
            </button>
            <div className="absolute right-0 top-full mt-1 bg-zinc-800 border-2 border-zinc-600 z-10 hidden group-hover/produce:block min-w-36"
              style={{ boxShadow: '3px 3px 0 0 #000' }}>
              <button onClick={() => handleProduce('draft')} className="w-full text-left px-3 py-2 text-retro text-zinc-300 hover:bg-zinc-700 border-b border-zinc-700" style={{ fontSize: '16px' }}>
                ▶ DRAFT (FAST)
              </button>
              <button onClick={() => handleProduce('quality')} className="w-full text-left px-3 py-2 text-retro text-zinc-300 hover:bg-zinc-700" style={{ fontSize: '16px' }}>
                ★ QUALITY (SLOW)
              </button>
            </div>
          </div>
        </div>
      </div>

      {expanded && (
        <div className="border-t-2 border-zinc-700 px-4 pb-4 pt-3">
          <div className="flex items-center justify-between mb-3">
            <span className="font-pixel text-zinc-500" style={{ fontSize: '7px' }}>
              SCENES {scenes ? `(${scenes.length})` : ''}
            </span>
            <button onClick={() => setSceneModal(null)} className="font-pixel text-accent-400 hover:text-accent-300" style={{ fontSize: '7px' }}>
              + ADD SCENE
            </button>
          </div>

          {loadingScenes ? (
            <div className="flex items-center justify-center py-6 gap-3">
              <span className="pixel-spinner" /><span className="text-retro text-zinc-500">LOADING SCENES...</span>
            </div>
          ) : scenes && scenes.length === 0 ? (
            <div className="text-center py-6">
              <p className="text-retro text-zinc-600 mb-2">NO SCENES YET</p>
              <button onClick={() => setSceneModal(null)} className="font-pixel text-accent-400 hover:text-accent-300" style={{ fontSize: '7px' }}>
                + ADD FIRST SCENE
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              {(scenes || []).map((scene, idx) => (
                <SceneRow key={scene.id} scene={{ ...scene, order_idx: idx }}
                  onEdit={() => setSceneModal(scene)}
                  onDelete={() => handleSceneDelete(scene)}
                  onRegenerate={handleRegenerate} />
              ))}
            </div>
          )}
        </div>
      )}

      {sceneModal !== false && (
        <SceneModal episodeId={episode.id} scene={sceneModal} locations={locations} characters={characters}
          onSave={() => { setSceneModal(false); refreshScenes() }} onClose={() => setSceneModal(false)} />
      )}
    </div>
  )
}

// ── Add Episode modal ────────────────────────────────────────────────────────

function AddEpisodeModal({ projectId, nextNumber, onSave, onClose }) {
  const [title, setTitle] = useState('')
  const [summary, setSummary] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    if (!title.trim()) return
    setSaving(true)
    try {
      await post(`/projects/${projectId}/episodes`, { number: nextNumber, title: title.trim(), summary: summary.trim() })
      onSave()
    } catch { alert('Failed to create episode.') }
    finally { setSaving(false) }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-pixel max-w-sm">
        <div className="modal-header">
          <span className="heading-pixel-sm text-accent-400">+ NEW EPISODE</span>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 font-pixel text-sm p-1">✕</button>
        </div>
        <div className="p-6 space-y-4">
          <div>
            <label className="label-pixel">EPISODE NUMBER</label>
            <input className="input-pixel w-20 text-center" type="number" defaultValue={nextNumber} disabled />
          </div>
          <div>
            <label className="label-pixel">TITLE</label>
            <input className="input-pixel" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Episode title" autoFocus />
          </div>
          <div>
            <label className="label-pixel">SUMMARY</label>
            <textarea className="input-pixel resize-none" rows={2} value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="Brief episode description..." />
          </div>
        </div>
        <div className="flex justify-end gap-3 px-6 py-4 border-t-2 border-zinc-700">
          <button onClick={onClose} className="btn-pixel-ghost">CANCEL</button>
          <button onClick={handleSave} disabled={!title.trim() || saving} className="btn-pixel">
            {saving ? 'CREATING...' : '+ CREATE EPISODE'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main ─────────────────────────────────────────────────────────────────────

export default function EpisodesTab({ projectId, project, episodes, onEpisodesChange, onProduce }) {
  const [showAddModal, setShowAddModal] = useState(false)
  const nextNumber = (episodes.length > 0 ? Math.max(...episodes.map((e) => e.number)) : 0) + 1

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="heading-pixel text-zinc-100 mb-1">📜 QUEST LOG</h2>
          <p className="text-retro text-zinc-500">
            {episodes.length} episode{episodes.length !== 1 ? 's' : ''}
            {episodes.length === 0 && ' — use OPTIONS → AI SCRIPT GENERATOR'}
          </p>
        </div>
        <button onClick={() => setShowAddModal(true)} className="btn-pixel">
          <Plus className="w-3 h-3" />NEW EPISODE
        </button>
      </div>

      {episodes.length === 0 ? (
        <div className="pixel-panel p-12 text-center">
          <div className="text-5xl mb-5">📜</div>
          <h3 className="heading-pixel text-zinc-300 mb-3">QUEST LOG EMPTY</h3>
          <p className="text-retro text-zinc-500 mb-8 max-w-sm mx-auto">
            Use <span className="text-zinc-200">OPTIONS → AI SCRIPT GENERATOR</span> to have Claude write your episodes, or add manually.
          </p>
          <button onClick={() => setShowAddModal(true)} className="btn-pixel">
            <Plus className="w-3 h-3" />ADD EPISODE MANUALLY
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {episodes.slice().sort((a, b) => a.number - b.number).map((ep) => (
            <EpisodeRow key={ep.id} episode={ep} project={project}
              onEpisodesChange={onEpisodesChange} onProduce={onProduce} />
          ))}
        </div>
      )}

      {showAddModal && (
        <AddEpisodeModal projectId={projectId} nextNumber={nextNumber}
          onSave={() => { setShowAddModal(false); onEpisodesChange() }}
          onClose={() => setShowAddModal(false)} />
      )}
    </div>
  )
}
