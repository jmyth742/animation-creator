import React, { useEffect, useState } from 'react'
import { Film, Play, ChevronDown, ChevronRight } from 'lucide-react'
import { get } from '../api/client'

function EpisodePlayer({ episode }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      className="bg-zinc-800 border-2 border-zinc-700 overflow-hidden"
      style={{ boxShadow: '3px 3px 0 0 #000' }}
    >
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-zinc-750"
        onClick={() => setExpanded((v) => !v)}
      >
        <button className="text-zinc-500 hover:text-accent-400 transition-colors">
          {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="font-pixel text-accent-500" style={{ fontSize: '7px' }}>
              EP {String(episode.number).padStart(2, '0')}
            </span>
            <span className="font-pixel text-zinc-100 truncate" style={{ fontSize: '8px' }}>
              {episode.title}
            </span>
          </div>
          {episode.summary && (
            <p className="text-retro text-zinc-500 line-clamp-1" style={{ fontSize: '15px' }}>
              {episode.summary}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="font-pixel text-zinc-600" style={{ fontSize: '6px' }}>
            {episode.scene_count} SCENE{episode.scene_count !== 1 ? 'S' : ''}
          </span>
          {episode.video_path ? (
            <span className="font-pixel text-px-green flex items-center gap-1" style={{ fontSize: '6px' }}>
              <Play className="w-2.5 h-2.5" /> READY
            </span>
          ) : (
            <span className="font-pixel text-zinc-600" style={{ fontSize: '6px' }}>
              NOT PRODUCED
            </span>
          )}
        </div>
      </div>

      {expanded && (
        <div className="border-t-2 border-zinc-700 p-4">
          {episode.video_path ? (
            <div>
              <video
                src={episode.video_path}
                controls
                className="w-full max-w-2xl mx-auto border-2 border-zinc-600"
                style={{ background: '#000' }}
              />
              <div className="flex items-center justify-center mt-3 gap-3">
                <a
                  href={episode.video_path}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-pixel-sm"
                >
                  <Play className="w-2.5 h-2.5" /> OPEN FULLSCREEN
                </a>
              </div>
            </div>
          ) : (
            <div className="text-center py-8">
              <Film className="w-8 h-8 text-zinc-700 mx-auto mb-3" />
              <p className="text-retro text-zinc-600 mb-1">NOT YET PRODUCED</p>
              <p className="text-retro text-zinc-700" style={{ fontSize: '14px' }}>
                Go to QUEST LOG and hit PRODUCE to generate this episode.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function TheaterTab({ projectId }) {
  const [episodes, setEpisodes] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchTheater = async () => {
      try {
        const data = await get(`/projects/${projectId}/theater`)
        setEpisodes(data)
      } catch {
        setEpisodes([])
      } finally {
        setLoading(false)
      }
    }
    fetchTheater()
  }, [projectId])

  const readyCount = episodes.filter((e) => e.video_path).length

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="heading-pixel text-zinc-100 mb-1">🎬 THEATER</h2>
          <p className="text-retro text-zinc-500">
            {readyCount} of {episodes.length} episode{episodes.length !== 1 ? 's' : ''} ready to watch
          </p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48 gap-4">
          <span className="pixel-spinner" />
          <span className="text-retro text-zinc-400">LOADING...</span>
        </div>
      ) : episodes.length === 0 ? (
        <div className="pixel-panel p-12 text-center">
          <div className="text-5xl mb-5">🎬</div>
          <h3 className="heading-pixel text-zinc-300 mb-3">NO EPISODES YET</h3>
          <p className="text-retro text-zinc-500 mb-8 max-w-sm mx-auto">
            Create episodes in the QUEST LOG tab, then PRODUCE them to watch here.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {episodes.map((ep) => (
            <EpisodePlayer key={ep.id} episode={ep} />
          ))}
        </div>
      )}
    </div>
  )
}
