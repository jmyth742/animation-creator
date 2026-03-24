import React, { useEffect, useState } from 'react'
import { History, Play, X, Clock, Wand2 } from 'lucide-react'
import { get } from '../api/client'

function VersionCard({ version, index }) {
  const [playing, setPlaying] = useState(false)

  const date = new Date(version.created_at)
  const dateStr = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  const timeStr = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })

  return (
    <div className="bg-zinc-900 border border-zinc-700 overflow-hidden" style={{ boxShadow: '2px 2px 0 0 #000' }}>
      {/* Video preview */}
      <div className="relative bg-black" style={{ aspectRatio: '16/9' }}>
        {version.preview_url ? (
          <video
            src={version.preview_url}
            autoPlay={playing}
            loop
            muted={!playing}
            playsInline
            controls={playing}
            className="w-full h-full object-cover cursor-pointer"
            onClick={() => setPlaying((v) => !v)}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <span className="font-pixel text-zinc-600" style={{ fontSize: '7px' }}>FILE MISSING</span>
          </div>
        )}
        {!playing && version.preview_url && (
          <div
            className="absolute inset-0 flex items-center justify-center bg-black/40 cursor-pointer hover:bg-black/20 transition-colors"
            onClick={() => setPlaying(true)}
          >
            <Play className="w-6 h-6 text-white drop-shadow" />
          </div>
        )}
        {/* Version badge */}
        <div className="absolute top-1 left-1 bg-black/80 px-1.5 py-0.5">
          <span className="font-pixel text-zinc-400" style={{ fontSize: '6px' }}>v{index + 1}</span>
        </div>
        {version.quality && (
          <div className="absolute top-1 right-1 bg-black/80 px-1.5 py-0.5">
            <span className="font-pixel text-zinc-400" style={{ fontSize: '6px' }}>{version.quality.toUpperCase()}</span>
          </div>
        )}
      </div>

      {/* Metadata */}
      <div className="p-3 space-y-2">
        <div className="flex items-center gap-1.5 text-zinc-500">
          <Clock className="w-2.5 h-2.5" />
          <span className="font-pixel" style={{ fontSize: '6px' }}>{dateStr} {timeStr}</span>
        </div>

        {version.visual_style && (
          <div>
            <div className="font-pixel text-zinc-600 mb-0.5" style={{ fontSize: '5px' }}>STYLE</div>
            <p className="text-retro text-zinc-400 line-clamp-2" style={{ fontSize: '13px' }}>
              {version.visual_style}
            </p>
          </div>
        )}

        {version.tone && (
          <div>
            <div className="font-pixel text-zinc-600 mb-0.5" style={{ fontSize: '5px' }}>TONE</div>
            <p className="text-retro text-zinc-400" style={{ fontSize: '13px' }}>{version.tone}</p>
          </div>
        )}

        {version.prompt && (
          <div>
            <div className="font-pixel text-zinc-600 mb-0.5" style={{ fontSize: '5px' }}>PROMPT SENT</div>
            <p className="text-retro text-zinc-500 line-clamp-3" style={{ fontSize: '12px' }}>
              {version.prompt}
            </p>
          </div>
        )}

        {version.seed_image && (
          <div className="flex items-center gap-1">
            <Wand2 className="w-2.5 h-2.5 text-zinc-600" />
            <span className="font-pixel text-zinc-600 truncate" style={{ fontSize: '5px' }}>
              seed: {version.seed_image.split('/').pop()}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

export default function SceneVersionsModal({ scene, onClose }) {
  const [versions, setVersions] = useState(null)
  const [loading, setLoading] = useState(true)

  const sceneLabel = `SCENE ${(scene.order_idx ?? 0) + 1}`

  useEffect(() => {
    get(`/scenes/${scene.id}/versions`)
      .then(setVersions)
      .catch(() => setVersions([]))
      .finally(() => setLoading(false))
  }, [scene.id])

  return (
    <div className="modal-overlay">
      <div className="modal-pixel w-full" style={{ maxWidth: '900px' }}>

        <div className="modal-header">
          <div className="flex items-center gap-3">
            <History className="w-4 h-4 text-accent-400" />
            <div>
              <span className="heading-pixel-sm text-accent-400">CLIP HISTORY</span>
              <span className="font-pixel text-zinc-500 ml-2" style={{ fontSize: '7px' }}>— {sceneLabel}</span>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 font-pixel text-sm p-1">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {loading && (
            <div className="flex items-center justify-center py-12 gap-3">
              <span className="pixel-spinner" />
              <span className="text-retro text-zinc-500">Loading history...</span>
            </div>
          )}

          {!loading && versions?.length === 0 && (
            <div className="text-center py-12">
              <History className="w-8 h-8 text-zinc-700 mx-auto mb-3" />
              <p className="font-pixel text-zinc-500 mb-1" style={{ fontSize: '7px' }}>NO HISTORY YET</p>
              <p className="text-retro text-zinc-600" style={{ fontSize: '15px' }}>
                Previous versions are saved automatically whenever you regenerate this clip.
              </p>
            </div>
          )}

          {!loading && versions?.length > 0 && (
            <div>
              <p className="text-retro text-zinc-500 mb-4" style={{ fontSize: '15px' }}>
                {versions.length} archived clip{versions.length !== 1 ? 's' : ''} — most recent first.
                Each was saved automatically before its replacement was generated.
              </p>
              <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}>
                {versions.map((v, i) => (
                  <VersionCard key={v.id} version={v} index={i} />
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-end px-6 py-4 border-t-2 border-zinc-700">
          <button onClick={onClose} className="btn-pixel">CLOSE</button>
        </div>
      </div>
    </div>
  )
}
