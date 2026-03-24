import React, { useEffect, useRef, useState } from 'react'
import { RefreshCw, CheckCircle, XCircle, Wand2, Film } from 'lucide-react'
import { post, get } from '../api/client'

// Generic progress modal used for both ref rebuilds and clip rebuilds
export default function RebuildRefsModal({ projectId, mode = 'refs', onClose, onComplete }) {
  const isRefs = mode === 'refs'
  const isClips = mode === 'clips'

  const [quality, setQuality] = useState('draft')
  const [phase, setPhase] = useState('confirm') // confirm | running | done | error
  const [jobId, setJobId] = useState(null)
  const [job, setJob] = useState(null)
  const [startError, setStartError] = useState('')
  const pollRef = useRef(null)

  const startUrl = isRefs
    ? `/projects/${projectId}/regenerate-references`
    : `/projects/${projectId}/regenerate-clips`
  const pollBase = isRefs
    ? `/projects/${projectId}/regenerate-references`
    : `/projects/${projectId}/regenerate-clips`

  const start = async () => {
    setPhase('running')
    setStartError('')
    try {
      const data = await post(isClips ? `${startUrl}?quality=${quality}` : startUrl)
      setJobId(data.job_id)
      setJob({ status: 'running', progress: 0, total: data.total, items: [] })
    } catch (err) {
      setStartError(err.response?.data?.detail || 'Failed to start. Is ComfyUI running?')
      setPhase('error')
    }
  }

  useEffect(() => {
    if (phase !== 'running' || !jobId) return

    pollRef.current = setInterval(async () => {
      try {
        const data = await get(`${pollBase}/${jobId}`)
        setJob(data)
        if (data.status === 'complete') {
          setPhase('done')
          clearInterval(pollRef.current)
          pollRef.current = null
        } else if (data.status === 'error') {
          setPhase('error')
          clearInterval(pollRef.current)
          pollRef.current = null
        }
      } catch {
        // ignore transient poll errors
      }
    }, 2000)

    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [phase, jobId, pollBase])

  const progress = job && job.total > 0 ? Math.round((job.progress / job.total) * 100) : 0
  const doneCount = job?.items?.filter((i) => i.status === 'done').length ?? 0
  const errorCount = job?.items?.filter((i) => i.status === 'error').length ?? 0

  const title = isRefs ? 'REBUILD ALL REFERENCES' : 'REGENERATE ALL CLIPS'
  const Icon = isRefs ? Wand2 : Film

  return (
    <div className="modal-overlay">
      <div className="modal-pixel max-w-lg w-full">

        <div className="modal-header">
          <div className="flex items-center gap-3">
            <Icon className="w-4 h-4 text-accent-400" />
            <span className="heading-pixel-sm text-accent-400">{title}</span>
          </div>
          {phase !== 'running' && (
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 font-pixel text-sm p-1">✕</button>
          )}
        </div>

        <div className="p-6 space-y-5">

          {/* ── CONFIRM ── */}
          {phase === 'confirm' && isRefs && (
            <div className="space-y-4">
              <p className="text-retro text-zinc-300" style={{ fontSize: '16px' }}>
                Regenerates FLUX reference images for <span className="text-accent-300">all characters and locations</span> using updated style-first prompts.
              </p>
              <div className="bg-zinc-900 border border-zinc-700 p-3 space-y-1.5">
                <div className="label-pixel mb-1">WHAT HAPPENS</div>
                <p className="text-retro text-zinc-400" style={{ fontSize: '15px' }}>• 3 FLUX candidates generated per character + location</p>
                <p className="text-retro text-zinc-400" style={{ fontSize: '15px' }}>• First candidate auto-selected as new canonical seed</p>
                <p className="text-retro text-zinc-400" style={{ fontSize: '15px' }}>• Visit Portrait / Location Studio to pick a different candidate</p>
                <p className="text-retro text-zinc-400" style={{ fontSize: '15px' }}>• ~15s per image — expect several minutes total</p>
              </div>
              <p className="text-retro text-amber-400" style={{ fontSize: '15px' }}>
                ⚠ Existing canonical reference images will be overwritten.
              </p>
            </div>
          )}

          {phase === 'confirm' && isClips && (
            <div className="space-y-4">
              <p className="text-retro text-zinc-300" style={{ fontSize: '16px' }}>
                Regenerates <span className="text-accent-300">every scene clip</span> across all episodes using current reference images as I2V seeds.
              </p>
              <div className="bg-zinc-900 border border-zinc-700 p-3 space-y-1.5">
                <div className="label-pixel mb-1">WHAT HAPPENS</div>
                <p className="text-retro text-zinc-400" style={{ fontSize: '15px' }}>• Each scene clip regenerated in episode order</p>
                <p className="text-retro text-zinc-400" style={{ fontSize: '15px' }}>• HunyuanVideo starts from the FLUX reference image (I2V seed)</p>
                <p className="text-retro text-zinc-400" style={{ fontSize: '15px' }}>• Style-first prompts applied — clips should match reference look</p>
                <p className="text-retro text-zinc-400" style={{ fontSize: '15px' }}>• ~45s per clip at draft quality</p>
                <p className="text-retro text-px-green" style={{ fontSize: '15px' }}>
                  ✓ Current clips are <span className="text-px-green font-bold">automatically archived</span> before replacement — nothing is lost
                </p>
              </div>
              <div className="bg-zinc-900 border border-zinc-700 p-3">
                <div className="label-pixel mb-1">VERSION CONTROL</div>
                <p className="text-retro text-zinc-400" style={{ fontSize: '15px' }}>
                  Each archived clip records the exact style, tone, prompt, and seed image used to generate it.
                  Compare versions using the <span className="text-amber-400">🕐 history button</span> on any scene row.
                </p>
              </div>
              <div>
                <div className="label-pixel mb-2">QUALITY</div>
                <div className="flex gap-2">
                  {[['draft', 'DRAFT (fast, ~45s)'], ['quality', 'QUALITY (slow, ~90s)']].map(([val, label]) => (
                    <button
                      key={val}
                      onClick={() => setQuality(val)}
                      className={`font-pixel border-2 px-3 py-1.5 transition-colors ${
                        quality === val
                          ? 'border-accent-400 text-accent-300 bg-accent-950'
                          : 'border-zinc-700 text-zinc-500 hover:border-zinc-500'
                      }`}
                      style={{ fontSize: '7px' }}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <p className="text-retro text-zinc-500" style={{ fontSize: '15px' }}>
                ⏱ This can take a long time for many scenes.
              </p>
            </div>
          )}

          {/* ── RUNNING / DONE ── */}
          {(phase === 'running' || phase === 'done') && job && (
            <div className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-pixel text-zinc-400" style={{ fontSize: '7px' }}>
                    {phase === 'done' ? 'COMPLETE' : 'PROCESSING...'}
                  </span>
                  <span className="font-pixel text-zinc-400" style={{ fontSize: '7px' }}>
                    {job.progress} / {job.total}
                  </span>
                </div>
                <div className="w-full bg-zinc-800 border border-zinc-700 h-3">
                  <div
                    className={`h-full transition-all duration-500 ${phase === 'done' ? 'bg-px-green' : 'bg-accent-500'}`}
                    style={{ width: `${progress}%` }}
                  />
                </div>
                {phase === 'running' && (
                  <p className="text-retro text-zinc-600 mt-1" style={{ fontSize: '14px' }}>
                    {isClips ? 'Each clip takes ~45s at draft quality.' : 'Each image takes ~15s.'} Don't close this window.
                  </p>
                )}
              </div>

              <div className="bg-zinc-900 border border-zinc-700 max-h-64 overflow-y-auto" style={{ scrollbarWidth: 'thin' }}>
                {job.items.length === 0 && (
                  <div className="flex items-center gap-2 px-3 py-2">
                    <span className="pixel-spinner" style={{ width: '10px', height: '10px' }} />
                    <span className="text-retro text-zinc-500" style={{ fontSize: '15px' }}>Starting...</span>
                  </div>
                )}
                {job.items.map((item, i) => (
                  <div key={i} className={`flex items-center gap-3 px-3 py-2 border-b border-zinc-800 last:border-0 ${item.status === 'running' ? 'bg-accent-950/30' : ''}`}>
                    {item.status === 'running' && <span className="pixel-spinner flex-shrink-0" style={{ width: '10px', height: '10px' }} />}
                    {item.status === 'done' && <CheckCircle className="w-3 h-3 text-px-green flex-shrink-0" />}
                    {item.status === 'error' && <XCircle className="w-3 h-3 text-px-red flex-shrink-0" />}
                    <div className="flex-1 min-w-0">
                      <span className={`text-retro ${item.status === 'done' ? 'text-zinc-400' : item.status === 'error' ? 'text-px-red' : 'text-zinc-200'}`} style={{ fontSize: '15px' }}>
                        {item.label}
                      </span>
                      {item.error && <p className="text-retro text-px-red" style={{ fontSize: '13px' }}>{item.error}</p>}
                    </div>
                  </div>
                ))}
              </div>

              {phase === 'done' && (
                <div className="bg-zinc-900 border border-px-green/30 p-3">
                  <p className="font-pixel text-px-green mb-1" style={{ fontSize: '7px' }}>
                    ✓ DONE — {doneCount} completed{errorCount > 0 ? `, ${errorCount} failed` : ''}
                  </p>
                  <p className="text-retro text-zinc-400" style={{ fontSize: '15px' }}>
                    {isRefs
                      ? 'Refresh the page to see updated references. Visit Portrait / Location Studio to pick a different candidate.'
                      : 'Refresh the page to see updated clips. Previous versions are saved — use the 🕐 history button on any scene row to compare.'}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* ── ERROR ── */}
          {phase === 'error' && (
            <div className="space-y-3">
              <div className="alert-error">✖ {startError || job?.error || 'An error occurred.'}</div>
              {(job?.items?.length ?? 0) > 0 && (
                <p className="text-retro text-zinc-500" style={{ fontSize: '15px' }}>{doneCount} completed before the error.</p>
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t-2 border-zinc-700">
          {phase === 'confirm' && (
            <>
              <button onClick={onClose} className="btn-pixel-ghost">CANCEL</button>
              <button onClick={start} className="btn-pixel flex items-center gap-2">
                <RefreshCw className="w-3 h-3" />
                {isRefs ? 'REBUILD ALL' : 'REGENERATE ALL'}
              </button>
            </>
          )}
          {phase === 'running' && (
            <span className="text-retro text-zinc-500 self-center" style={{ fontSize: '15px' }}>Running — please wait...</span>
          )}
          {(phase === 'done' || phase === 'error') && (
            <button onClick={() => { onComplete?.(); onClose() }} className="btn-pixel">
              {phase === 'done' ? '✓ CLOSE & REFRESH' : 'CLOSE'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
