import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Plus, Camera, ChevronDown, ChevronRight, Trash2, Pencil, Play, X, Eye, Film, RefreshCw, Star, MapPin, Users, History } from 'lucide-react'
import { get, post, put, del } from '../api/client'
import SceneStudioModal from './SceneStudioModal'
import SceneComposerModal from './SceneComposerModal'
import SceneVersionsModal from './SceneVersionsModal'

// ── Scene timeline strip ──────────────────────────────────────────────────────

function SceneTimeline({ scenes, locations, characters, onSelectScene, onAddScene }) {
  const locMap = Object.fromEntries((locations || []).map((l) => [l.id, l]))
  const charMap = Object.fromEntries((characters || []).map((c) => [c.id, c]))

  return (
    <div className="border-b-2 border-zinc-700 bg-zinc-900 px-4 py-3">
      <div className="flex items-center gap-1 overflow-x-auto pb-1" style={{ scrollbarWidth: 'thin' }}>
        {(scenes || []).map((scene, idx) => {
          const loc = locMap[scene.location_id]
          const sceneChars = (scene.characters || []).map((c) => charMap[c.id]).filter(Boolean)
          const isGenerating = scene.status === 'generating'
          const isDone = scene.status === 'done'

          return (
            <React.Fragment key={scene.id}>
              {idx > 0 && (
                <div className="flex-shrink-0 text-zinc-700" style={{ fontSize: '10px' }}>▶</div>
              )}
              <button
                onClick={() => onSelectScene(scene, idx)}
                className="flex-shrink-0 flex flex-col border-2 overflow-hidden transition-all hover:border-accent-500 group/card"
                style={{
                  width: '72px',
                  minHeight: '56px',
                  background: '#111',
                  borderColor: isDone ? '#22c55e33' : isGenerating ? '#818cf8' : '#3f3f46',
                  boxShadow: '2px 2px 0 0 #000',
                }}
                title={scene.visual || `Scene ${idx + 1}`}
              >
                {/* Location thumbnail */}
                <div className="relative w-full flex-shrink-0 overflow-hidden" style={{ height: '38px' }}>
                  {loc?.reference_url ? (
                    <img src={loc.reference_url} alt={loc.name} className="w-full h-full object-cover opacity-80 group-hover/card:opacity-100" />
                  ) : scene.reference_url ? (
                    <img src={scene.reference_url} alt="ref" className="w-full h-full object-cover opacity-80 group-hover/card:opacity-100" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center bg-zinc-800">
                      <Film className="w-3 h-3 text-zinc-600" />
                    </div>
                  )}
                  {/* Scene number badge */}
                  <div className="absolute top-0.5 left-0.5 bg-black/70 px-1">
                    <span className="font-pixel text-zinc-300" style={{ fontSize: '5px' }}>S{idx + 1}</span>
                  </div>
                  {isGenerating && (
                    <div className="absolute inset-0 bg-accent-500/20 flex items-center justify-center">
                      <span className="pixel-spinner" style={{ width: '8px', height: '8px' }} />
                    </div>
                  )}
                </div>

                {/* Character avatars */}
                <div className="flex items-center gap-0.5 px-1 py-0.5 flex-wrap">
                  {sceneChars.slice(0, 4).map((c) => (
                    <div
                      key={c.id}
                      className="flex-shrink-0 border border-zinc-600 overflow-hidden flex items-center justify-center"
                      style={{ width: '12px', height: '16px', background: '#0d1117' }}
                      title={c.name}
                    >
                      {c.portrait_url ? (
                        <img src={c.portrait_url} alt={c.name} className="w-full h-full object-cover" />
                      ) : (
                        <span className="font-pixel text-zinc-500" style={{ fontSize: '5px' }}>
                          {c.name.slice(0, 1)}
                        </span>
                      )}
                    </div>
                  ))}
                  {sceneChars.length === 0 && (
                    <Users className="w-2.5 h-2.5 text-zinc-700" />
                  )}
                  {sceneChars.length > 4 && (
                    <span className="font-pixel text-zinc-600" style={{ fontSize: '5px' }}>+{sceneChars.length - 4}</span>
                  )}
                </div>
              </button>
            </React.Fragment>
          )
        })}

        {/* Add scene button */}
        <div className="flex-shrink-0 text-zinc-700 ml-1" style={{ fontSize: '10px' }}>▶</div>
        <button
          onClick={onAddScene}
          className="flex-shrink-0 border-2 border-dashed border-zinc-700 hover:border-accent-500 flex flex-col items-center justify-center gap-1 transition-colors"
          style={{ width: '72px', minHeight: '56px' }}
          title="Add new scene"
        >
          <Plus className="w-3 h-3 text-zinc-600" />
          <span className="font-pixel text-zinc-600" style={{ fontSize: '5px' }}>ADD</span>
        </button>
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

function SceneRow({ scene, onEdit, onDelete, onRegenerate, onOpenSceneStudio, onOpenHistory }) {
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
        <div className="flex items-start gap-3">

          {/* Reference image thumbnail — clickable shortcut to Scene Studio */}
          <div
            className={`flex-shrink-0 border overflow-hidden cursor-pointer mt-0.5 ${
              scene.reference_url ? 'border-px-green' : 'border-dashed border-zinc-700 hover:border-zinc-500'
            }`}
            style={{ width: '48px', height: '27px', background: '#111' }}
            onClick={onOpenSceneStudio}
            title={scene.reference_url ? 'Scene reference set — click to edit' : 'Add scene reference'}
          >
            {scene.reference_url ? (
              <img src={scene.reference_url} alt="ref" className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <Camera className="w-2.5 h-2.5 text-zinc-700" />
              </div>
            )}
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap gap-2 mb-1.5">
              {scene.location_name && <span className="badge-pixel">📍 {scene.location_name}</span>}
              <span className="badge-pixel">{scene.clip_length?.toUpperCase()}</span>
              <span className={`font-pixel flex items-center gap-1 ${statusColor}`} style={{ fontSize: '7px' }}>
                {isGenerating && <span className="pixel-spinner" style={{ width: '8px', height: '8px' }} />}
                {scene.status?.toUpperCase()}
              </span>
              {scene.reference_url && (
                <span className="font-pixel text-px-green flex items-center gap-0.5" style={{ fontSize: '6px' }}>
                  <Star className="w-2 h-2 fill-current" /> SCENE REF
                </span>
              )}
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
                  autoPlay loop muted playsInline
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
            <button
              onClick={onOpenHistory}
              className="p-1.5 border border-zinc-600 text-zinc-400 hover:text-amber-400 hover:border-amber-600"
              title="Clip history — compare previous versions">
              <History className="w-3 h-3" />
            </button>
            <button
              onClick={onOpenSceneStudio}
              className="p-1.5 border border-zinc-600 text-zinc-400 hover:text-px-green hover:border-px-green"
              title="Scene Studio — generate reference image">
              <Camera className="w-3 h-3" />
            </button>
            <div className="relative group/regen">
              <button
                onClick={() => onRegenerate(scene, 'draft', 0.82)}
                disabled={isGenerating}
                className="p-1.5 border border-zinc-600 text-zinc-400 hover:text-accent-400 hover:border-accent-600 disabled:opacity-40 disabled:cursor-not-allowed"
                title="Regenerate clip">
                <RefreshCw className={`w-3 h-3 ${isGenerating ? 'animate-spin' : ''}`} />
              </button>
              <div className="absolute right-0 top-full mt-1 bg-zinc-800 border-2 border-zinc-600 z-20 hidden group-hover/regen:block min-w-48"
                style={{ boxShadow: '3px 3px 0 0 #000' }}>
                <div className="px-3 pt-2 pb-1">
                  <p className="font-pixel text-zinc-600" style={{ fontSize: '5px' }}>DRAFT (FAST)</p>
                </div>
                <button onClick={() => onRegenerate(scene, 'draft', 0.70)}
                  className="w-full text-left px-3 py-1.5 text-retro text-zinc-300 hover:bg-zinc-700" style={{ fontSize: '15px' }}>
                  ⟳ FAITHFUL
                </button>
                <button onClick={() => onRegenerate(scene, 'draft', 0.82)}
                  className="w-full text-left px-3 py-1.5 text-retro text-zinc-300 hover:bg-zinc-700" style={{ fontSize: '15px' }}>
                  ⟳ BALANCED
                </button>
                <button onClick={() => onRegenerate(scene, 'draft', 1.0)}
                  className="w-full text-left px-3 py-1.5 text-retro text-zinc-300 hover:bg-zinc-700 border-b border-zinc-700" style={{ fontSize: '15px' }}>
                  ⟳ CREATIVE
                </button>
                <div className="px-3 pt-2 pb-1">
                  <p className="font-pixel text-zinc-600" style={{ fontSize: '5px' }}>QUALITY (SLOW)</p>
                </div>
                <button onClick={() => onRegenerate(scene, 'quality', 0.70)}
                  className="w-full text-left px-3 py-1.5 text-retro text-zinc-300 hover:bg-zinc-700" style={{ fontSize: '15px' }}>
                  ★ FAITHFUL
                </button>
                <button onClick={() => onRegenerate(scene, 'quality', 0.82)}
                  className="w-full text-left px-3 py-1.5 text-retro text-zinc-300 hover:bg-zinc-700" style={{ fontSize: '15px' }}>
                  ★ BALANCED
                </button>
                <button onClick={() => onRegenerate(scene, 'quality', 1.0)}
                  className="w-full text-left px-3 py-1.5 text-retro text-zinc-300 hover:bg-zinc-700" style={{ fontSize: '15px' }}>
                  ★ CREATIVE
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
  const [sceneStudio, setSceneStudio] = useState(null)
  const [sceneHistory, setSceneHistory] = useState(null)
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

  const handleRegenerate = async (scene, quality, denoise = 0.82) => {
    try {
      await post(`/scenes/${scene.id}/regenerate?quality=${quality}&denoise=${denoise}`)
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

  const handleProduce = async (quality, force = false, denoise = 0.82) => {
    setProducing(true)
    try {
      const result = await post(`/episodes/${episode.id}/produce?quality=${quality}&force=${force}&denoise=${denoise}`)
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
            <div className="absolute right-0 top-full mt-1 bg-zinc-800 border-2 border-zinc-600 z-10 hidden group-hover/produce:block min-w-56"
              style={{ boxShadow: '3px 3px 0 0 #000' }}>
              <div className="px-3 pt-2 pb-1">
                <p className="font-pixel text-zinc-600 mb-1" style={{ fontSize: '5px' }}>DRAFT (FAST)</p>
              </div>
              <button onClick={() => handleProduce('draft', false, 0.70)} className="w-full text-left px-3 py-1.5 text-retro text-zinc-300 hover:bg-zinc-700" style={{ fontSize: '15px' }}>
                ▶ FAITHFUL <span className="text-zinc-600 ml-1">— close to refs</span>
              </button>
              <button onClick={() => handleProduce('draft', false, 0.82)} className="w-full text-left px-3 py-1.5 text-retro text-zinc-300 hover:bg-zinc-700" style={{ fontSize: '15px' }}>
                ▶ BALANCED <span className="text-zinc-600 ml-1">— default</span>
              </button>
              <button onClick={() => handleProduce('draft', false, 1.0)} className="w-full text-left px-3 py-1.5 text-retro text-zinc-300 hover:bg-zinc-700 border-b border-zinc-700" style={{ fontSize: '15px' }}>
                ▶ CREATIVE <span className="text-zinc-600 ml-1">— full freedom</span>
              </button>
              <div className="px-3 pt-2 pb-1">
                <p className="font-pixel text-zinc-600 mb-1" style={{ fontSize: '5px' }}>QUALITY (SLOW)</p>
              </div>
              <button onClick={() => handleProduce('quality', false, 0.70)} className="w-full text-left px-3 py-1.5 text-retro text-zinc-300 hover:bg-zinc-700" style={{ fontSize: '15px' }}>
                ★ FAITHFUL <span className="text-zinc-600 ml-1">— close to refs</span>
              </button>
              <button onClick={() => handleProduce('quality', false, 0.82)} className="w-full text-left px-3 py-1.5 text-retro text-zinc-300 hover:bg-zinc-700" style={{ fontSize: '15px' }}>
                ★ BALANCED <span className="text-zinc-600 ml-1">— default</span>
              </button>
              <button onClick={() => handleProduce('quality', false, 1.0)} className="w-full text-left px-3 py-1.5 text-retro text-zinc-300 hover:bg-zinc-700 border-b border-zinc-700" style={{ fontSize: '15px' }}>
                ★ CREATIVE <span className="text-zinc-600 ml-1">— full freedom</span>
              </button>
              <div className="px-3 pt-2 pb-1">
                <p className="font-pixel text-zinc-600 mb-1" style={{ fontSize: '5px' }}>FORCE REGENERATE (rebuilds chain)</p>
              </div>
              <button onClick={() => handleProduce('draft', true, 0.82)} className="w-full text-left px-3 py-1.5 text-retro text-amber-400 hover:bg-zinc-700 border-b border-zinc-700" style={{ fontSize: '15px' }}>
                ↺ DRAFT + REGEN ALL
              </button>
              <button onClick={() => handleProduce('quality', true, 0.82)} className="w-full text-left px-3 py-1.5 text-retro text-amber-400 hover:bg-zinc-700" style={{ fontSize: '15px' }}>
                ↺ QUALITY + REGEN ALL
              </button>
            </div>
          </div>
        </div>
      </div>

      {expanded && (
        <>
          {/* Timeline strip — shown once scenes are loaded */}
          {scenes && (
            <SceneTimeline
              scenes={scenes}
              locations={locations}
              characters={characters}
              onSelectScene={(scene, idx) => setSceneModal({ ...scene, order_idx: idx })}
              onAddScene={() => setSceneModal(null)}
            />
          )}

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
                    onEdit={() => setSceneModal({ ...scene, order_idx: idx })}
                    onDelete={() => handleSceneDelete(scene)}
                    onRegenerate={handleRegenerate}
                    onOpenSceneStudio={() => setSceneStudio({ ...scene, order_idx: idx })}
                    onOpenHistory={() => setSceneHistory({ ...scene, order_idx: idx })} />
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {sceneModal !== false && (
        <SceneComposerModal
          episodeId={episode.id}
          scene={sceneModal}
          locations={locations}
          characters={characters}
          projectContext={{
            series_title: project.title,
            visual_style: project.visual_style,
            tone: project.tone,
            setting: project.setting,
            premise: project.premise,
          }}
          onSave={() => { setSceneModal(false); refreshScenes() }}
          onClose={() => setSceneModal(false)}
        />
      )}

      {sceneHistory && (
        <SceneVersionsModal
          scene={sceneHistory}
          onClose={() => setSceneHistory(null)}
        />
      )}

      {sceneStudio && (
        <SceneStudioModal
          scene={sceneStudio}
          project={project}
          locations={locations}
          onClose={() => setSceneStudio(null)}
          onReferenceSelected={(updated) => {
            setSceneStudio(updated)
            setScenes((prev) => prev
              ? prev.map((s) => s.id === updated.id ? { ...s, ...updated } : s)
              : prev
            )
          }}
        />
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
