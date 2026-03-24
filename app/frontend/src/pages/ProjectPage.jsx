import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Users, Tv, MapPin, Settings, RefreshCw, Film } from 'lucide-react'
import { get } from '../api/client'
import CharactersTab from '../components/CharactersTab'
import EpisodesTab from '../components/EpisodesTab'
import LocationsTab from '../components/LocationsTab'
import ProjectSettingsForm from '../components/ProjectSettingsForm'
import ProductionPanel from '../components/ProductionPanel'
import RebuildRefsModal from '../components/RebuildRefsModal'

const TABS = [
  { key: 'characters', label: 'PARTY',     Icon: Users   },
  { key: 'locations',  label: 'WORLD MAP', Icon: MapPin  },
  { key: 'episodes',   label: 'QUEST LOG', Icon: Tv      },
  { key: 'settings',   label: 'OPTIONS',   Icon: Settings },
]

export default function ProjectPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('characters')
  const [activeJobId, setActiveJobId] = useState(null)
  const [activeJobMeta, setActiveJobMeta] = useState(null)
  const [rebuildRefsOpen, setRebuildRefsOpen] = useState(false)
  const [rebuildClipsOpen, setRebuildClipsOpen] = useState(false)

  const fetchProject = async () => {
    try {
      const data = await get(`/projects/${id}`)
      setProject(data)
    } catch (err) {
      setError('Failed to load project.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchProject() }, [id]) // eslint-disable-line

  const handleCharactersChange = () => fetchProject()
  const handleEpisodesChange = () => fetchProject()
  const handleLocationsChange = () => fetchProject()
  const handleProjectUpdate = (updated) => setProject(updated)

  const handleProduce = (jobId, meta) => {
    setActiveJobId(jobId)
    setActiveJobMeta(meta)
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center gap-4">
        <span className="pixel-spinner" />
        <span className="text-retro text-zinc-400">LOADING...</span>
      </div>
    )
  }

  if (error || !project) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="pixel-panel p-8 text-center max-w-sm">
          <div className="text-4xl mb-4">💀</div>
          <p className="text-retro text-px-red mb-4">{error || 'GAME OVER — Project not found.'}</p>
          <button onClick={() => navigate('/')} className="btn-pixel-ghost">
            ◀ BACK TO MENU
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="scanlines min-h-screen bg-zinc-950 flex flex-col">

      {/* Header */}
      <header className="bg-zinc-900 border-b-2 border-zinc-700 sticky top-0 z-10"
        style={{ boxShadow: '0 4px 0 0 #000' }}>
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="text-zinc-400 hover:text-accent-400 p-1.5 transition-colors border-2 border-transparent hover:border-zinc-600"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="font-pixel text-accent-400 truncate" style={{ fontSize: '10px', textShadow: '1px 1px 0 #000' }}>
              {project.title}
            </h1>
            {project.tone && (
              <p className="text-retro text-zinc-500 text-sm truncate">{project.tone}</p>
            )}
          </div>
        </div>

        {/* Tabs + rebuild button */}
        <div className="max-w-7xl mx-auto px-6 flex items-end justify-between">
          <nav className="flex gap-0 -mb-px">
            {TABS.map(({ key, label, Icon }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={`tab-pixel flex items-center gap-2 ${activeTab === key ? 'active' : ''}`}
              >
                <Icon className="w-3 h-3" />
                {label}
              </button>
            ))}
          </nav>
          <div className="flex items-center gap-2 mb-1">
            <button
              onClick={() => setRebuildRefsOpen(true)}
              className="btn-pixel-ghost flex items-center gap-1.5"
              title="Regenerate all character + location reference images with FLUX"
            >
              <RefreshCw className="w-3 h-3" />
              REBUILD REFS
            </button>
            <button
              onClick={() => setRebuildClipsOpen(true)}
              className="btn-pixel-ghost flex items-center gap-1.5"
              title="Regenerate all scene clips using updated references as I2V seeds"
            >
              <Film className="w-3 h-3" />
              REGEN ALL CLIPS
            </button>
          </div>
        </div>
      </header>

      {/* Tab content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-8">
        {activeTab === 'characters' && (
          <CharactersTab
            projectId={id}
            characters={project.characters || []}
            onCharactersChange={handleCharactersChange}
          />
        )}
        {activeTab === 'locations' && (
          <LocationsTab
            projectId={id}
            project={project}
            locations={project.locations || []}
            onLocationsChange={handleLocationsChange}
          />
        )}
        {activeTab === 'episodes' && (
          <EpisodesTab
            projectId={id}
            project={project}
            episodes={project.episodes || []}
            onEpisodesChange={handleEpisodesChange}
            onProduce={handleProduce}
          />
        )}
        {activeTab === 'settings' && (
          <ProjectSettingsForm project={project} onUpdate={handleProjectUpdate} />
        )}
      </main>

      {rebuildRefsOpen && (
        <RebuildRefsModal
          projectId={id}
          mode="refs"
          onClose={() => setRebuildRefsOpen(false)}
          onComplete={fetchProject}
        />
      )}

      {rebuildClipsOpen && (
        <RebuildRefsModal
          projectId={id}
          mode="clips"
          onClose={() => setRebuildClipsOpen(false)}
          onComplete={fetchProject}
        />
      )}

      {activeJobId && activeJobMeta && (
        <ProductionPanel
          jobId={activeJobId}
          episodeTitle={activeJobMeta.episodeTitle}
          seriesSlug={activeJobMeta.seriesSlug}
          episodeNumber={activeJobMeta.episodeNumber}
          onClose={() => { setActiveJobId(null); setActiveJobMeta(null) }}
        />
      )}
    </div>
  )
}
