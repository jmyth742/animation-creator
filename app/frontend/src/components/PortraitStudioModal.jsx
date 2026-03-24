import React, { useState } from 'react'
import { Wand2, Star, X, RefreshCw } from 'lucide-react'
import { post } from '../api/client'

function getInitials(name = '') {
  return name.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase()
}

export default function PortraitStudioModal({ character, onClose, onPortraitSelected }) {
  const [generating, setGenerating] = useState(false)
  const [candidates, setCandidates] = useState([]) // relative paths
  const [selecting, setSelecting] = useState(null)
  const [canonicalPath, setCanonicalPath] = useState(character.reference_image_path ?? null)
  const [error, setError] = useState('')

  const handleGenerate = async () => {
    setGenerating(true)
    setError('')
    setCandidates([])
    try {
      const data = await post(`/characters/${character.id}/generate-portrait`)
      const relativePaths = (data.portrait_urls || []).map((url) =>
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
      const updated = await post(`/characters/${character.id}/select-portrait`, {
        portrait_path: relativePath,
      })
      setCanonicalPath(updated.reference_image_path)
      onPortraitSelected(updated)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to set portrait.')
    } finally {
      setSelecting(null)
    }
  }

  // All portraits to show in the picker: new candidates take priority, fall back to just the canonical
  const displayCandidates = candidates.length > 0
    ? candidates
    : canonicalPath ? [canonicalPath] : []

  return (
    <div className="modal-overlay">
      <div className="modal-pixel max-w-2xl w-full">

        {/* Header */}
        <div className="modal-header">
          <div className="flex items-center gap-3">
            <span className="text-lg">🎨</span>
            <div>
              <span className="heading-pixel-sm text-accent-400">PORTRAIT STUDIO</span>
              <span className="font-pixel text-zinc-500 ml-2" style={{ fontSize: '7px' }}>
                — {character.name.toUpperCase()}
              </span>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 font-pixel text-sm p-1">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="flex gap-6">

            {/* Left — current canonical portrait */}
            <div className="flex-shrink-0 flex flex-col items-center gap-3">
              <div className="font-pixel text-zinc-500 text-center" style={{ fontSize: '7px' }}>
                {canonicalPath ? '★ CANONICAL' : 'NO PORTRAIT'}
              </div>
              <div
                className={`w-40 h-40 border-2 flex items-center justify-center overflow-hidden flex-shrink-0 ${
                  canonicalPath ? 'border-px-green' : 'border-zinc-600 border-dashed'
                }`}
                style={{ boxShadow: '3px 3px 0 0 #000', background: '#1c1c38' }}
              >
                {canonicalPath ? (
                  <img
                    src={`/static/series/${canonicalPath}`}
                    alt={character.name}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <span className="font-pixel text-accent-400" style={{ fontSize: '32px', textShadow: '2px 2px 0 #000' }}>
                    {getInitials(character.name)}
                  </span>
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
                  {character.visual_description || (
                    <span className="text-zinc-600 italic">No visual description — add one in character settings first.</span>
                  )}
                </p>
              </div>

              {/* Generate button */}
              <div className="flex items-center gap-3">
                <button
                  onClick={handleGenerate}
                  disabled={generating || !character.visual_description}
                  className="btn-pixel flex items-center gap-2 disabled:opacity-50"
                >
                  {generating
                    ? <><span className="pixel-spinner" /> GENERATING...</>
                    : <><Wand2 className="w-3 h-3" /> {candidates.length > 0 ? 'REGENERATE' : 'GENERATE PORTRAITS'}</>
                  }
                </button>
                {generating && (
                  <span className="text-retro text-zinc-500" style={{ fontSize: '15px' }}>
                    Running HunyuanVideo... (~30s per candidate)
                  </span>
                )}
              </div>

              {!character.visual_description && (
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
                    {candidates.length > 0 ? 'CHOOSE YOUR CANONICAL PORTRAIT:' : 'CURRENT PORTRAIT:'}
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
                          style={{ width: '120px', height: '120px', boxShadow: '2px 2px 0 0 #000' }}
                          title={isCanonical ? 'Current canonical portrait' : 'Click to use as canonical'}
                        >
                          <img
                            src={`/static/series/${relPath}`}
                            alt={`Candidate ${i + 1}`}
                            className="w-full h-full object-cover"
                          />

                          {/* Selected overlay */}
                          {isCanonical && (
                            <div className="absolute inset-0 bg-px-green/20 flex flex-col items-center justify-center gap-1">
                              <Star className="w-6 h-6 text-px-green fill-current drop-shadow-lg" />
                              <span className="font-pixel text-px-green" style={{ fontSize: '6px', textShadow: '1px 1px 0 #000' }}>
                                CANONICAL
                              </span>
                            </div>
                          )}

                          {/* Loading overlay */}
                          {isSelecting && (
                            <div className="absolute inset-0 bg-black/70 flex items-center justify-center">
                              <span className="pixel-spinner" />
                            </div>
                          )}

                          {/* Hover select hint */}
                          {!isCanonical && !isSelecting && (
                            <div className="absolute inset-0 bg-accent-500/0 hover:bg-accent-500/30 transition-all flex items-end justify-center pb-2 opacity-0 hover:opacity-100">
                              <span className="font-pixel text-white bg-black/80 px-2 py-0.5" style={{ fontSize: '6px' }}>
                                USE THIS
                              </span>
                            </div>
                          )}

                          {/* Candidate number */}
                          {!isCanonical && (
                            <div className="absolute top-1 left-1 bg-black/70 px-1">
                              <span className="font-pixel text-zinc-400" style={{ fontSize: '6px' }}>#{i + 1}</span>
                            </div>
                          )}
                        </button>
                      )
                    })}

                    {/* Regenerate more */}
                    {candidates.length > 0 && (
                      <button
                        onClick={handleGenerate}
                        disabled={generating}
                        className="flex-shrink-0 border-2 border-dashed border-zinc-600 hover:border-zinc-400 flex flex-col items-center justify-center gap-2 transition-colors disabled:opacity-40"
                        style={{ width: '120px', height: '120px' }}
                        title="Generate 3 more candidates"
                      >
                        <RefreshCw className="w-5 h-5 text-zinc-500" />
                        <span className="font-pixel text-zinc-500" style={{ fontSize: '6px' }}>MORE</span>
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* First-time empty state */}
              {displayCandidates.length === 0 && !generating && (
                <div className="border-2 border-dashed border-zinc-700 p-6 text-center">
                  <div className="text-3xl mb-2">🎨</div>
                  <p className="font-pixel text-zinc-500 mb-1" style={{ fontSize: '7px' }}>NO PORTRAITS GENERATED YET</p>
                  <p className="text-retro text-zinc-600" style={{ fontSize: '15px' }}>
                    Click Generate Portraits to create candidates using HunyuanVideo.
                    You'll get 3 options to choose from.
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
              ? 'Canonical portrait is set — this image seeds video generation for consistency.'
              : 'Set a canonical portrait to ensure visual consistency across all episodes.'}
          </div>
          <button onClick={onClose} className="btn-pixel">DONE</button>
        </div>

      </div>
    </div>
  )
}
