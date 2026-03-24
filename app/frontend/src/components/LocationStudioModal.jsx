import React, { useState } from 'react'
import { MapPin, Star, RefreshCw, Wand2 } from 'lucide-react'
import { post } from '../api/client'

export default function LocationStudioModal({ location, project, onClose, onReferenceSelected }) {
  const [generating, setGenerating] = useState(false)
  const [candidates, setCandidates] = useState([])
  const [selecting, setSelecting] = useState(null)
  const [canonicalPath, setCanonicalPath] = useState(location.reference_image_path ?? null)
  const [error, setError] = useState('')

  const handleGenerate = async () => {
    setGenerating(true)
    setError('')
    setCandidates([])
    try {
      const data = await post(`/locations/${location.id}/generate-reference`)
      const relativePaths = (data.reference_urls || []).map((url) =>
        url.replace(/^\/static\/series\//, '')
      )
      setCandidates(relativePaths)
    } catch (err) {
      setError(err.response?.data?.detail || 'Generation failed. Is ComfyUI running?')
    } finally {
      setGenerating(false)
    }
  }

  const handleSelect = async (relativePath) => {
    setSelecting(relativePath)
    setError('')
    try {
      const updated = await post(`/locations/${location.id}/select-reference`, {
        reference_path: relativePath,
      })
      setCanonicalPath(updated.reference_image_path)
      onReferenceSelected(updated)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to set reference image.')
    } finally {
      setSelecting(null)
    }
  }

  const displayCandidates = candidates.length > 0
    ? candidates
    : canonicalPath ? [canonicalPath] : []

  return (
    <div className="modal-overlay">
      <div className="modal-pixel max-w-3xl w-full">

        {/* Header */}
        <div className="modal-header">
          <div className="flex items-center gap-3">
            <span className="text-lg">🗺</span>
            <div>
              <span className="heading-pixel-sm text-accent-400">LOCATION STUDIO</span>
              <span className="font-pixel text-zinc-500 ml-2" style={{ fontSize: '7px' }}>
                — {location.name.toUpperCase()}
              </span>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 font-pixel text-sm p-1">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="flex gap-6">

            {/* Left — current canonical reference */}
            <div className="flex-shrink-0 flex flex-col items-center gap-3">
              <div className="font-pixel text-zinc-500 text-center" style={{ fontSize: '7px' }}>
                {canonicalPath ? '★ CANONICAL' : 'NO REFERENCE'}
              </div>
              <div
                className={`border-2 flex items-center justify-center overflow-hidden flex-shrink-0 ${
                  canonicalPath ? 'border-px-green' : 'border-zinc-600 border-dashed'
                }`}
                style={{ width: '192px', height: '128px', boxShadow: '3px 3px 0 0 #000', background: '#1c1c38' }}
              >
                {canonicalPath ? (
                  <img
                    src={`/static/series/${canonicalPath}`}
                    alt={location.name}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <MapPin className="w-8 h-8 text-zinc-600" />
                )}
              </div>
              {canonicalPath && (
                <div className="flex items-center gap-1">
                  <Star className="w-3 h-3 text-px-green fill-current" />
                  <span className="font-pixel text-px-green" style={{ fontSize: '7px' }}>IN USE</span>
                </div>
              )}
            </div>

            {/* Right — controls + candidates */}
            <div className="flex-1 flex flex-col gap-4">

              {/* Visual description */}
              <div>
                <div className="label-pixel mb-1">VISUAL DESCRIPTION</div>
                <p className="text-retro text-zinc-400 bg-zinc-900 border border-zinc-700 p-2"
                  style={{ fontSize: '15px', lineHeight: '1.5' }}>
                  {location.description || (
                    <span className="text-zinc-600 italic">No description — add one in location settings first.</span>
                  )}
                </p>
              </div>

              {/* Project style context */}
              {(project?.visual_style || project?.setting) && (
                <div>
                  <div className="label-pixel mb-1">PROJECT AESTHETIC (injected into prompt)</div>
                  <div className="bg-zinc-900 border border-zinc-700 p-2 space-y-1">
                    {project.visual_style && (
                      <p className="text-retro text-zinc-500" style={{ fontSize: '14px' }}>
                        <span className="text-zinc-600">Style: </span>{project.visual_style}
                      </p>
                    )}
                    {project.setting && (
                      <p className="text-retro text-zinc-500" style={{ fontSize: '14px' }}>
                        <span className="text-zinc-600">Setting: </span>{project.setting}
                      </p>
                    )}
                    {project.tone && (
                      <p className="text-retro text-zinc-500" style={{ fontSize: '14px' }}>
                        <span className="text-zinc-600">Mood: </span>{project.tone}
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Generate button */}
              <div className="flex items-center gap-3">
                <button
                  onClick={handleGenerate}
                  disabled={generating || !location.description}
                  className="btn-pixel flex items-center gap-2 disabled:opacity-50"
                >
                  {generating
                    ? <><span className="pixel-spinner" /> GENERATING...</>
                    : <><Wand2 className="w-3 h-3" /> {candidates.length > 0 ? 'REGENERATE' : 'GENERATE REFERENCES'}</>
                  }
                </button>
                {generating && (
                  <span className="text-retro text-zinc-500" style={{ fontSize: '15px' }}>
                    Running HunyuanVideo... (~30s per candidate)
                  </span>
                )}
              </div>

              {!location.description && (
                <p className="text-retro text-amber-500" style={{ fontSize: '15px' }}>
                  ⚠ Add a visual description first so the AI knows what to generate.
                </p>
              )}

              {error && (
                <div className="alert-error">✖ {error}</div>
              )}

              {/* Candidates grid */}
              {displayCandidates.length > 0 && (
                <div>
                  <div className="label-pixel mb-2">
                    {candidates.length > 0 ? 'CHOOSE YOUR CANONICAL REFERENCE:' : 'CURRENT REFERENCE:'}
                  </div>
                  <div className="flex flex-wrap gap-3">
                    {displayCandidates.map((relPath, i) => {
                      const isCanonical = relPath === canonicalPath
                      const isSelecting = selecting === relPath

                      return (
                        <button
                          key={i}
                          onClick={() => !isCanonical && handleSelect(relPath)}
                          disabled={isSelecting || isCanonical}
                          className={`relative flex-shrink-0 border-2 overflow-hidden transition-all ${
                            isCanonical
                              ? 'border-px-green cursor-default'
                              : 'border-zinc-600 hover:border-accent-400 hover:scale-105'
                          }`}
                          style={{ width: '160px', height: '107px', boxShadow: '2px 2px 0 0 #000' }}
                          title={isCanonical ? 'Current canonical reference' : 'Click to use as canonical'}
                        >
                          <img
                            src={`/static/series/${relPath}`}
                            alt={`Candidate ${i + 1}`}
                            className="w-full h-full object-cover"
                          />

                          {isCanonical && (
                            <div className="absolute inset-0 bg-px-green/20 flex flex-col items-center justify-center gap-1">
                              <Star className="w-6 h-6 text-px-green fill-current drop-shadow-lg" />
                              <span className="font-pixel text-px-green" style={{ fontSize: '6px', textShadow: '1px 1px 0 #000' }}>
                                CANONICAL
                              </span>
                            </div>
                          )}

                          {isSelecting && (
                            <div className="absolute inset-0 bg-black/70 flex items-center justify-center">
                              <span className="pixel-spinner" />
                            </div>
                          )}

                          {!isCanonical && !isSelecting && (
                            <div className="absolute inset-0 bg-accent-500/0 hover:bg-accent-500/30 transition-all flex items-end justify-center pb-2 opacity-0 hover:opacity-100">
                              <span className="font-pixel text-white bg-black/80 px-2 py-0.5" style={{ fontSize: '6px' }}>
                                USE THIS
                              </span>
                            </div>
                          )}

                          {!isCanonical && (
                            <div className="absolute top-1 left-1 bg-black/70 px-1">
                              <span className="font-pixel text-zinc-400" style={{ fontSize: '6px' }}>#{i + 1}</span>
                            </div>
                          )}
                        </button>
                      )
                    })}

                    {candidates.length > 0 && (
                      <button
                        onClick={handleGenerate}
                        disabled={generating}
                        className="flex-shrink-0 border-2 border-dashed border-zinc-600 hover:border-zinc-400 flex flex-col items-center justify-center gap-2 transition-colors disabled:opacity-40"
                        style={{ width: '160px', height: '107px' }}
                        title="Generate 3 more candidates"
                      >
                        <RefreshCw className="w-5 h-5 text-zinc-500" />
                        <span className="font-pixel text-zinc-500" style={{ fontSize: '6px' }}>MORE</span>
                      </button>
                    )}
                  </div>
                </div>
              )}

              {displayCandidates.length === 0 && !generating && (
                <div className="border-2 border-dashed border-zinc-700 p-6 text-center">
                  <div className="text-3xl mb-2">📍</div>
                  <p className="font-pixel text-zinc-500 mb-1" style={{ fontSize: '7px' }}>NO REFERENCE GENERATED YET</p>
                  <p className="text-retro text-zinc-600" style={{ fontSize: '15px' }}>
                    Click Generate References to create location stills using HunyuanVideo.
                    The canonical image seeds wide/establishing shots for visual consistency.
                  </p>
                </div>
              )}

            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t-2 border-zinc-700">
          <div className="text-retro text-zinc-600" style={{ fontSize: '14px' }}>
            {canonicalPath
              ? 'Canonical reference set — used as the I2V seed for establishing & wide shots in this location.'
              : 'Set a reference image to anchor the visual style of wide and establishing shots.'}
          </div>
          <button onClick={onClose} className="btn-pixel">DONE</button>
        </div>

      </div>
    </div>
  )
}
